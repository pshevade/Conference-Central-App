#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

$Id$

created by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from conference import ConferenceApi
from google.appengine.api import memcache

MEMCACHE_SPEAKER_NAME_KEY = "FEATURED_SPEAKER_NAME"
MEMCACHE_SPEAKER_COUNT_KEY = "FEATURED_SPEAKER_COUNT"
MEMCACHE_FEATURED_KEY = "FEATURED_SPEAKER"
ANNOUNCEMENT_TPL = ('Check out this session by %s!')


class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        ConferenceApi._cacheAnnouncement()
        self.response.set_status(204)


class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )


class SetFeaturedSpeaker(webapp2.RequestHandler):

    def post(self):
        """Set the featured speaker here"""
        # print "Speaker is: ", self.request.speaker
        # print "Have spoken how often: ", self.request.count
        _cacheFeaturedSpeaker(self.request.get('speaker'), self.request.get('count'))


def _cacheFeaturedSpeaker(speaker, count):
    """Create featured speaker announcement & assign to memcache; used by
    """
    print "Inside cacheFeaturedSpeaker"
    exisiting_speaker_count = memcache.get(MEMCACHE_SPEAKER_COUNT_KEY)
    print "this is the existing speaker count: ", exisiting_speaker_count
    if count >= exisiting_speaker_count:
        featured_speaker = ANNOUNCEMENT_TPL % speaker
        memcache.set(MEMCACHE_FEATURED_KEY, featured_speaker)
        memcache.set(MEMCACHE_SPEAKER_NAME_KEY, speaker)
        memcache.set(MEMCACHE_SPEAKER_COUNT_KEY, count)
    # If there are no sold out conferences,
    # delete the memcache announcements entry
    # featured_speaker = ""
    # memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

    return featured_speaker

app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/set_featured_speaker', SetFeaturedSpeaker),
], debug=True)
