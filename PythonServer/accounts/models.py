import timedelta
import urllib
import os
from django.db import models
from django.contrib.auth.models import User
from ios_notifications.models import APNService, Notification, Device
from notifications.api import createNotification, sendNotification
from django.core.files import File

GENDER = (
    ('male', 'Male'),
    ('female', 'Female'),
)

# Create your models here.
class Account(models.Model):
    user = models.OneToOneField(User)
    user_name = models.CharField(max_length=255, unique=True)
    display_name = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=255, null=True, blank=True, unique=True)
    email = models.CharField(max_length=255, unique=True)
    facebook_id = models.CharField(max_length=255, null=True, blank=True)
    bio = models.CharField(max_length=255, null=True, blank=True)
    uber = models.CharField(max_length=255, null=True, blank=True)
    profile_pic =  models.ImageField(upload_to="upload/facebook/pf_pic", null=True, blank=True)
    gender = models.CharField(max_length=255, null=True, blank=True, choices=GENDER)
    birthday = models.DateField(null=True,blank=True)
    home_town = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.NullBooleanField(default=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)
    def __unicode__(self):
        return str('{0} : {1} {2}'.format(self.user_name,self.first_name, self.last_name))
    def save(self, user=None, *args, **kwargs):
        if self.pk:
            if not self.display_name:
                self.display_name = '{0} {1}'.format(self.first_name, self.last_name)
        super(Account, self).save()


class UserLocation(models.Model):
    account = models.ForeignKey(Account)
    longitude = models.FloatField()
    latitude = models.FloatField()

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)
    def __unicode__(self):
        return str("{0} : {1},{2}".format(self.account.user_name, self.longitude, self.latitude))


class FacebookProfile(models.Model):
    user = models.ForeignKey(Account)
    facebook_id = models.CharField(max_length=150)
    profilePicture = models.ImageField(upload_to="upload/facebook", null=True, blank=True)
    image_url = models.URLField()
    access_token = models.CharField(max_length=255)
    helpdesk = models.NullBooleanField(default=True)
    notifications = models.NullBooleanField(default=True)
    active = models.NullBooleanField(default=False)
    issue = models.NullBooleanField(default=True)
    polls = models.NullBooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)

    def is_active(self):
        return active

    def deactivate(self):
        helpdesk = False
        notifications = False
        active = False
        self.save()

    def get_remote_image(self):
        if self.image_url and not self.profilePicture:
            result = urllib.urlretrieve(self.image_url)
            self.profilePicture.save(os.path.basename(self.image_url),File(open(result[0])))
            self.save()

    def update_token(self, token):
        self.access_token = token
        self.save()


class VenmoProfile(models.Model):
    user = models.ForeignKey(Account)
    venmo_id = models.CharField(max_length=150)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    access_token = models.CharField(max_length=255, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)

    def update_token(self, token):
        self.access_token = token
        self.save()


class VenmoTransaction(models.Model):
    charger = models.ForeignKey(VenmoProfile, related_name='charger')
    charged = models.ForeignKey(VenmoProfile, related_name='charged')
    payment_id = models.CharField(max_length=255)
    note = models.CharField(max_length=255, null=True, blank=True)
    amount = models.FloatField()
    date_created = models.DateTimeField(null=True, blank=True)
    date_completed = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)


class AccountDeviceID(models.Model):
    account = models.ForeignKey(Account)
    device_id = models.CharField(max_length=255, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)


class AccountSettings(models.Model):
    account = models.OneToOneField(Account)
    private = models.NullBooleanField(default=False)
    searchable = models.NullBooleanField(default=True)
    reminder_on = models.NullBooleanField(default=True)
    reminder_delta = timedelta.fields.TimedeltaField(null=True,blank=True)
    vibrate_on_notification = models.NullBooleanField(default=True)
    allow_charge = models.NullBooleanField(default=False, null=True,blank=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)


class AccountSetting(models.Model):
    account = models.ForeignKey(Account)
    setting_name = models.CharField(max_length=255)
    setting_value = models.CharField(max_length=255, null=True, blank=True)

    created = models.DateField(auto_now_add=True, null=True, blank=True)    # NOW
    modified = models.DateField(auto_now=True)                              # auto update time

    class Meta:
        unique_together = (('account', 'setting_name'),)


class FriendRequest(models.Model):
    account_user = models.ForeignKey(Account, related_name='friend_requester')
    friend = models.ForeignKey(Account, related_name='friend_recieving_request')
    resolved = models.NullBooleanField(default=False)
    ignore = models.NullBooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateField(auto_now=True)

    def __unicode__(self):
        return str('{0} requested {1} to friend'.format(self.account_user.user_name,self.friend.user_name))
    class Meta:
        unique_together = (('account_user', 'friend'),)


class AccountLink(models.Model):
    account_user = models.ForeignKey(Account, related_name='account_user')
    friend = models.ForeignKey(Account, related_name='friend')
    invited_count = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)
    blocked = models.NullBooleanField(default=False)

    def save(self, create_notification=None, *args, **kwargs):
        if not self.pk and create_notification:
            try:
                user = self.account_user.user
                message = "You have just been joined by {0} on Meep".format(self.friend.user_name)
                custom_payload = {"joined_by_name": friend.user_name, "joined_by_id": friend.id}
                custom_payload = json.dumps(custom_payload)
                notification = createNotification(message, custom_payload)
                notification.recipients.add(user)
                addNotificationToRedis(notification, self.account_user.id)
                tokens = []
                device = Device.objects.get(users__pk=user.id)
                tokens.append(device.token)
                sendNotification(notification, tokens)
            except Exception as e:
                print 'Unable to send push notification when {0} tried adding friend {1}'.format(self.account_user, self.friend)
        super(AccountLink, self).save()

    def __unicode__(self):
        return str('{0} : {1}'.format(self.account_user.user_name,self.friend.user_name))
    class Meta:
        unique_together = (('account_user', 'friend'),)
    

class Group(models.Model):
    group_creator = models.ForeignKey(Account, related_name='group_creator') 
    name = models.CharField(max_length=255)
    members = models.ManyToManyField(Account)
    is_active = models.NullBooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)
    def __unicode__(self):
        return str('{0} : {1}'.format(self.name,self.group_creator.id))
    class Meta:
        unique_together = (('group_creator', 'name'),)
