import json
import logging
import pickle
import simplejson
import ast
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader, Context, RequestContext
from django.contrib.auth.decorators import login_required
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.models import User
from accounts.models import Account, AccountLink
from accounts.api import pushToNOSQLSet, pushToNOSQLHash
from models import Event, EventComment, EventNotification, InvitedFriend
from rediscli import r as R

logger = logging.getLogger("django.request")


def checkIfAuthorized(event, account):
    is_authorized = False
    # Make sure user is authorized to leave a comment on this event
    if event.creator == account:
        is_authorized = True

    if not is_authorized:
        try:
            invited_friend = InvitedFriend.objects.get(event=event, user=account)
            is_authorized = True
        except:
            pass
    return is_authorized


@login_required
def getEvent(request, event_id):
    rtn_dict = {'success': False, "msg": ""}

    try:
        account = Account.objects.get(user=request.user)
        event = Event.objects.get(pk=event_id)
        is_authorized = checkIfAuthorized(event, account)
        if is_authorized:
            r = R.r
            redis_event_key = 'event.{0}.hash'.format(event_id)
            redis_event = r.hgetall(redis_event_key)
            redis_invited_friends_key = 'event.{0}.invited_friends.set'.format(event_id)
            redis_invited_friends = r.zrange(redis_invited_friends_key, 0, 10)
            if not redis_event and not redis_invited_friends:
                invited_friends_list = []
                invited_friends = InvitedFriend.objects.filter(event=event)
                for invited_friend in invited_friends:
                    invited_friends_list.append(model_to_dict(invited_friend))
                rtn_dict['invited_friends'] = invited_friends_list
                rtn_dict['event'] = model_to_dict(event)
            else:
                rtn_dict['invited_friends'] = redis_invited_friends
                rtn_dict['event'] = redis_event
            rtn_dict['success'] = True
            rtn_dict['msg'] = 'successfully got event'
    except Exception as e:
        print e
        logger.info('Error grabbing events {0}: {1}'.format(event_id, e))
        rtn_dict['msg'] = 'Error grabbing events {0}: {1}'.format(event_id, e)
    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def upcomingEvents(request, account_id):
    rtn_dict = {'success': False, "msg": ""}
    try:
        r = R.r
        upcoming_events_key = 'account.{0}.events.set'.format(account_id)
        upcoming_events = r.zrange(upcoming_events_key, 0, 10)
        owned_upcoming_events_key = 'account.{0}.owned_events.set'.format(account_id)
        owned_upcoming_events = r.zrange(owned_upcoming_events_key, 0, 10)

        if not upcoming_events:
            upcoming_events = []
            owned_events = Event.objects.filter(creator=account_id).order_by('start_time')
            for event in owned_events:
                if not event.event_over and not event.cancelled:
                    upcoming_events.append(model_to_dict(event)) 

            invited_users = InvitedFriend.objects.select_related('event').filter(user=account_id)
            for invited_user in invited_users:
                if not invited_user.event.event_over and not invited_user.event.cancelled:
                    if invited_user.event.creator != account_id:
                        upcoming_events.append(model_to_dict(invited_user.event))
        rtn_dict['upcoming_events'] = upcoming_events
        rtn_dict['owned_upcoming_events'] = owned_upcoming_events
        rtn_dict['success'] = True
        rtn_dict['message'] = 'Successfully retrieved upcoming events'
    except Exception as e:
        print 'Error grabbing upcoming events: {0}'.format(e)
        logger.info('Error grabbing upcoming events: {0}'.format(e))
        rtn_dict['msg'] = 'Error grabbing upcoming events: {0}'.format(e)

    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def createEvent(request):
    rtn_dict = {'success': False, "msg": ""}
    if request.method == 'POST':
        try:
            user = Account.objects.get(user=request.user)
            event = Event(creator=user)
            event.name = request.POST['name']
            event.start_time = request.POST['start_time']
            event.end_time = request.POST['end_time']
            event.description = request.POST['description']
            event.location_name = request.POST['location_name']
            event.location_address = request.POST['location_address']
            event.location_coordinates = request.POST['location_coordinates']
            event.event_over = request.POST['event_over']
            event.friends_can_invite = request.POST['friends_can_invite'] # not saving nullboolean fields correctly 
            event.cancelled = request.POST['cancelled']
            event.private = request.POST['private']
            event.save()

            r = R.r
            redis_key = 'event.{0}.hash'.format(event.id)
            r.hmset(redis_key, model_to_dict(event))

            created_events_key = 'account.{0}.owned_events.set'.format(user.id)
            event_dict = {'event_id': event.id, 'event_name': event.name, 'start_time': str(event.start_time)}
            event_dict = json.dumps(event_dict)
            pushToNOSQLSet(created_events_key, event_dict, 0)

            try:
                invited_friends = request.POST['invited_friends']
                for user_dict in invited_friends:
                    try:
                        # save user link to event
                        user_id = user_dict['user_id']
                        can_invite_friends = user_dict['can_invite_friends']
                        friend = Account.objects.get(pk=user_id)
                        invited_friend = InvitedFriend(event=event, user=friend, can_invite_friends=can_invite_friends)
                        invited_friend.save()

                        account_link = AccountLink.objects.get(account_user=user, friend=friend)
                        account_link.invited_count += 1
                        account_link.save()

                        redis_friend_key = 'event.{0}.invited_friends.set'.format(event.id)
                        invited_friend_dict = json.dumps({
                                                'invited_friend_id': invited_friend.id,
                                                'friend_id':friend.id,
                                                'pf_pic': friend.profile_pic,
                                                'name': friend.display_name,
                                                "attending": False})
                        pushToNOSQLSet(redis_friend_key, invited_friend_dict, account_link.invited_count)
                        redis_user_events_key = 'account.{0}.events.set'.format(friend.id)
                        event_dict = json.dumps({'event_id': event.id, 
                                        'event_name': event.name,
                                        'start_time': str(event.start_time)})
                        pushToNOSQLSet(redis_user_events_key, event_dict, 0)
                    except Exception as e:
                        logger.info('Error adding user {0}: {1}'.format(user,e))
            except Exception as e:
                logger.info('Error inviting friends: {0}'.format(e))

            rtn_dict['success'] = True
            rtn_dict['msg'] = 'Successfully created new user event!'

        except Exception as e:
            print 'Error creating new event: {0}'.format(e)
            logger.info('Error creating new event: {0}'.format(e))
            rtn_dict['msg'] = 'Error creating new event: {0}'.format(e)

    else:
        rtn_dict['msg'] = 'Not POST'
    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def inviteFriends(request, event_id):
    rtn_dict = {'success': False, "msg": ""}
    is_authorized = False
    if request.method == 'POST':
        try:
            invited_friends = ast.literal_eval(json.loads(request.POST['invited_friends']))
            event = Event.objects.get(pk=event_id)

            # check to see if this use is allowed to invite more friends to event
            try:
                account = Account.objects.get(user=request.user)
                if event.creator == account:
                    is_authorized = True
            except:
                pass

            if not is_authorized:
                try:
                    invited_friend = InvitedFriend.objects.get(event=Event, user=account)
                    if inivited_friend.can_invite_friends:
                        is_authorized = True
                except:
                    pass

            if is_authorized:
                r = R.r
                for user_dict in invited_friends:
                    try:
                        #print user_dict
                        user_id = user_dict['user_id']
                        can_invite_friends = user_dict['can_invite_friends']
                        friend = Account.objects.get(pk=user_id)
                        invited_friend = InvitedFriend(event=event, user=friend, can_invite_friends=can_invite_friends)
                        invited_friend.save()

                        account_link = AccountLink.objects.get(account_user=account, friend=friend)
                        account_link.invited_count += 1
                        account_link.save()

                        #Save to Redis
                        redis_key = 'event.{0}.invited_friends.set'.format(event_id)
                        invited_friend_dict = json.dumps({
                                                'invited_friend_id': invited_friend.id,
                                                'friend_id':friend.id,
                                                'pf_pic': friend.profile_pic,
                                                'name': friend.display_name,
                                                "attending": False})
                        pushToNOSQLSet(redis_key, invited_friend_dict, account_link.invited_count)
                        redis_user_events_key = 'account.{0}.events.set'.format(friend.id)
                        event_dict = json.dumps({
                                        'event_id': event.id,
                                        'event_name': event.name,
                                        'start_time': str(event.start_time)})
                        pushToNOSQLSet(redis_user_events_key, event_dict, 0)
                        rtn_dict['success'] = True
                        rtn_dict['msg'] = 'Successfully added users'
                    except Exception as e:
                        #print 'Error adding user {0}'.format(e)
                        logger.info('Error adding user {0}'.format(e))
                        rtn_dict['msg'] = 'Error adding user {0}'.format(e)
                
            else:
                rtn_dict['msg'] = 'user is not authorized to invite other friends'
        except Exception as e:
            print 'Error inviting friends: {0}'.format(e)
            logger.info('Error inviting friends: {0}'.format(e))
            rtn_dict['msg'] = 'Error inviting friends: {0}'.format(e)

    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def updateEvent(request, event_id):
    rtn_dict = {'success': False, "msg": ""}
    try:
        event = Event.objects.get(pk=event_id)
        r = R.r
        redis_key = 'event.{0}.hash'.format(event_id)
        try:
            event.name = request.POST['name']
        except:
            pass
        try:
            event.start_time = request.POST['start_time']
        except:
            pass
        try:
            event.end_time = request.POST['end_time']
        except:
            pass
        try:
            event.description = request.POST['description']
        except:
            pass
        try:
            event.location_name = request.POST['location_name']
        except:
            pass
        try:
            event.location_address = request.POST['location_address']
        except:
            pass
        try:
            event.location_coordinates = request.POST['location_coordinates']
        except:
            pass
        try:
            event.friends_can_invite = request.POST['friends_can_invite']
        except:
            pass

        event.save()
        pushToNOSQLHash(redis_key, model_to_dict(event))
        rtn_dict['success'] = True
        rtn_dict['msg'] = 'Successfully updated {0}!'.format(event.name)
    except Exception as e:
        logger.info('Error updating event {0}: {1}'.format(event_id, e))
        rtn_dict['msg'] = 'Error updating event {0}: {1}'.format(event_id, e)
    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def selectAttending(request, event_id):
    rtn_dict = {'success': False, "msg": ""}

    if request.method == 'POST':
        try:
            user = Account.objects.get(user=request.user)
            event = Event.objects.get(pk=event_id)
            invited_friend = InvitedFriend.objects.get(event=event, user=user)
            if request.POST['attending']:
                invited_friend.attending = True
            else:
                invited_friend.attending = False
            invited_friend.save()
        except Exception as e:
            logger.info('Error selected attending for event {0}: user {1}'.format(event.id, user.id , e))
            rtn_dict['msg'] = 'Error selected attending for event {0}: user {1}'.format(event.id, user.id , e)

    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def createEventComment(request, event_id):
    rtn_dict = {'success': False, "msg": ""}
    if request.method == 'POST':
        try:
            account = Account.objects.get(user=request.user)
            event = Event.objects.get(pk=event_id)
            is_authorized = checkIfAuthorized(event, account)
            if is_authorized:
                new_comment = EventComment(event=event,user=account)
                new_comment.description = request.POST['description']
                new_comment.save()
                r = R.r
                redis_key = 'event.{0}.comments.set'.format(event_id)
                new_comment_dict = model_to_dict(new_comment)
                comment_dict = json.dumps(new_comment_dict)
                pushToNOSQLSet(redis_key, comment_dict, 0)

                rtn_dict['success'] = True
                rtn_dict['msg'] = 'successfully created comment for event {0}'.format(event_id)
            else:
                logger.info('user not authorized to create event comments')
                rtn_dict['msg'] = 'user not authorized to create event comments'
        except Exception as e:
            logger.info('Error creating event comment: {0}'.format(e))
            rtn_dict['msg'] = 'Error creating event comment: {0}'.format(e)
    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")


@login_required
def getEventComments(request, event_id):
    rtn_dict = {'success': False, "msg": ""}
    try:
        r = R.r
        redis_key = 'event.{0}.comments.set'.format(event_id)
        comments = r.zrange(redis_key, 0, 10)

        if not comments:
            comments = []
            account = Account.objects.get(user=request.user)
            event = Event.objects.get(pk=event_id)
            is_authorized = checkIfAuthorized(event, account)

            event_comments = EventComment.objects.filter(event=event)

            for event_comment in event_comments:
                comments.append(model_to_dict(event_comment))

        rtn_dict['comments'] = comments
        rtn_dict['success'] = True
        rtn_dict['msg'] = 'successfully retrieved comments for event {0}'.format(event_id)
    except Exception as e:
        logger.info('Error retrieving event comments: {0}'.format(e))
        rtn_dict['msg'] = 'Error retrieving event comments: {0}'.format(e)
    return HttpResponse(json.dumps(rtn_dict, cls=DjangoJSONEncoder), content_type="application/json")