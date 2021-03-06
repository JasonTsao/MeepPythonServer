import json
import logging
import pickle
import simplejson
import ast
from celery import task
from django.contrib.auth.decorators import login_required
from django.forms.models import model_to_dict
from django.contrib.auth.models import User
from accounts.models import Account, AccountLink
from accounts.api import pushToNOSQLSet, pushToNOSQLHash
#from notifications.api import eventPushNotification, sendPushNotification
from events.models import Event, EventComment, EventNotification, InvitedFriend
from rediscli import r as R

logger = logging.getLogger("django.request")


@task
def populateUserFriends(account_id):
	try:
		r = R.r
		r_user_friends_key = 'account.{0}.friends.set'.format(account_id)
		r.delete(r_user_friends_key)
		friends_list = []
		friend_links = AccountLink.objects.select_related('friend').filter(account_user=request.user).order_by('invited_count')
		for link in friend_links:
			if link.friend.is_active:
				friend_dict = json.loads(model_to_dict(link.friend))
	    		pushToNOSQLSet(r_user_friends_key, friend_dict, False, link.friend.invited_count)
	except Exception as e:
		print 'Error populating NOSQL layer with invited friends for event {0}: {1}'.format(event_id, e)
		return False
	return True


@task
def populateUser(account_id):
	try:
		r = R.r
		r_user_key = 'account.{0}.hash'.format(user_id)
		user = Account.objects.get(pk=account_id)
		r.hmset(model_to_dict(user))
	except Exception as e:
		print 'Error populating NOSQL layer with user {0}: {1}'.format(account_id, e)
		return False


@task
def populateUserGroups(account_id):
	try:
		r = R.r
		r_user_groups_key = 'account.{0}.groups.set'.format(account_id)
		r.delete(r_user_groups_key)
		groups = Group.objects.filter(members__id=account_id)
		for group in groups:
			pushToNOSQLSet(r_user_groups_key, model_to_dict(group), False, 0)
	except Exception as e:
		print 'Error populating NOSQL layer with user {0} groups: {1}'.format(account_id, e)
		return False
	return True


@task
def populateGroup(group_id):
	try:
		r = R.r
		r_group_key = 'group.{0}.hash'.format(group_id)
		group = Group.objects.get(pk=group_id)
		r.hmset(model_to_dict(group))
	except Exception as e:
		print 'Error populating NOSQL layer with group {0}: {1}'.format(group_id, e)
		return False

	return True