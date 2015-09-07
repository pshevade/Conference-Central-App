#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import ProfileForms
from models import StringMessage
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import SessionQueryForm
from models import SessionQueryForms
from models import TeeShirtSize
from models import Session
from models import SessionForm
from models import SessionForms
from models import TypeOfSession
from models import Speaker

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')
MEMCACHE_FEATURED_KEY = "FEATURED_SPEAKER"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
}

DEFAULTS_SESSION = {
    "highlights": "Certainly an awesome session!",
    "duration": 0,
    "type_of_session": "NOT_SPECIFIED",
}

OPERATORS = {
    'EQ':   '=',
    'GT':   '>',
    'GTEQ': '>=',
    'LT':   '<',
    'LTEQ': '<=',
    'NE':   '!='
}

FIELDS =    {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }

FIELDS_SESSION =    {
            'DURATION': 'duration',
            'DATE': 'date',
            'START_TIME': 'start_time',
            'TYPE_OF_SESSION': 'type_of_session',
            }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_GET_BY_TYPE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    typeOfSession=messages.StringField(2),
)

SESSION_GET_BY_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1),
)

SESSION_GET_BY_WISHLIST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_GET_BY_KEY = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(1),
)

SESSION_GET_BY_CONFERENCE_DATE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    date=messages.StringField(2),
)

PROFILE_GET_BY_SESSION_IN_WISHLISHT = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(2),
)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return request


    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
            http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)


    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)


    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        print "****** inside get conference, how'd we get here?"
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='getConferencesCreated',
            http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, getattr(prof, 'displayName')) for conf in confs]
        )


    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatFilters(self, filters, SESS_OR_CONF='conf'):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None
        extra_inequality_filters = []
        print "Trying to format filters"
        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}
            try:
                if SESS_OR_CONF == 'conf':
                    filtr["field"] = FIELDS[filtr["field"]]
                elif SESS_OR_CONF == 'sess':
                    filtr["field"] = FIELDS_SESSION[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")
            # Every operation except "=" is an inequality - check only for conferences
            if filtr["operator"] != "=":
                print "checking equality operator"
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    extra_inequality_filters.append(filtr)
                else:
                    inequality_field = filtr["field"]
                    formatted_filters.append(filtr)
            else:
                formatted_filters.append(filtr)
            print "Done formatting one filter set"
        print "Filters formatted just fine"
        if SESS_OR_CONF == 'conf':
            return (inequality_field, formatted_filters)
        else:
            return (inequality_field, formatted_filters, extra_inequality_filters)


    @endpoints.method(ConferenceQueryForms, ConferenceForms,
            path='queryConferences',
            http_method='POST',
            name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)
        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in \
                conferences]
        )

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = p_key,
                displayName = user.nickname(),
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        #if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        #else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)


    @endpoints.method(message_types.VoidMessage, ProfileForm,
            path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()


    @endpoints.method(ProfileMiniForm, ProfileForm,
            path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement


    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='conference/announcement/get',
            http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")


    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='sessions/featuredspeaker/get',
            http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_FEATURED_KEY) or "")

# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='conferences/attending',
            http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser() # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])\
         for conf in conferences]
        )


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='filterPlayground',
            http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.city=="London")
        q = q.filter(Conference.topics=="Medical Innovations")
        q = q.filter(Conference.month==6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )


# -- FINAL PROJECT METHODS -- #

    @endpoints.method(PROFILE_GET_BY_SESSION_IN_WISHLISHT, ProfileForms,
        path='session/{sessionKey}/wishlist/everyone',
        http_method='GET', name='getProfilesBySessionWishlist')
    def getProfilesBySessionWishList(self, request):
        """ Return all profiles who want to attend a particular session. """
        session = ndb.Key(urlsafe=request.sessionKey).get()
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % request.sessionKey)
        profiles = Profile.query().filter(Profile.session_wish_list == session.key.urlsafe())

        return ProfileForms(
            profiles=[self._copyProfileToForm(profile) for profile in profiles])

    @endpoints.method(SESSION_GET_BY_CONFERENCE_DATE, SessionForms,
        path='conference/{websafeConferenceKey}/{date}/sessions',
        http_method='GET', name='getConferenceSessionsByDate')
    def getConferenceSessionsByDate(self, request):
        """ Return the sessions that occur on a conference's particular date """
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        date = datetime.strptime(request.date[:10], "%Y-%m-%d").date()
        if not conf:
            raise endpoints.NotFoundException(
                'No conf found with key: %s' % request.websafeConferenceKey)
        sessions = Session.query(ancestor=conf.key).filter(Session.date==date)
        return SessionForms(
            items=[self._copySessionToForm(session, conf) for session in sessions]
        )


    @endpoints.method(SESSION_GET_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/sessions',
        http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Return requested conference (by websafeSessionKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conf found with key: %s' % request.websafeConferenceKey)
        sessions = Session.query(ancestor=conf.key)
        return SessionForms(
            items=[self._copySessionToForm(session, conf) for session in sessions]
        )

    def _copySessionToForm(self, session, conf):
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(session, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'date':
                    setattr(sf, field.name, getattr(session, field.name).strftime("%Y-%m-%d"))
                elif field.name == 'start_time':
                    setattr(sf, field.name, getattr(session, field.name).strftime("%H:%M"))
                elif field.name == 'type_of_session':
                    try:
                        setattr(sf, field.name, getattr(TypeOfSession, getattr(session, field.name)))
                    except AttributeError:
                        setattr(sf, field.name, getattr(TypeOfSession, 'NOT_SPECIFIED'))
                else:
                    setattr(sf, field.name, getattr(session, field.name))
            elif field.name == "conf_websafekey":
                setattr(sf, field.name, conf.key.urlsafe())
            elif field.name == "sess_websafekey":
                setattr(sf, field.name, session.key.urlsafe())
        sf.check_initialized()
        return sf

    @endpoints.method(SESSION_GET_BY_TYPE_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/sessions/type/{typeOfSession}',
        http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conf found with key: %s' % request.websafeConferenceKey)
        items = []
        sessions = Session.query(ancestor=conf.key).filter(Session.type_of_session==request.typeOfSession)
        return SessionForms(
            items=[self._copySessionToForm(session, conf) for session in sessions]
        )
        return SessionForms(items=items)

    @endpoints.method(SESSION_GET_BY_SPEAKER, SessionForms,
        path='sessions/speaker/{speaker}',
        http_method='GET', name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        print "****** We are inside getSessionsBySpeaker"
        conferences = Conference.query()
        items = []
        speaker_set = Speaker.query().filter(Speaker.name==request.speaker)
        for speaker in speaker_set:
            for conf in conferences:
                sessions = Session.query(ancestor=conf.key).filter(Session.speaker_key==speaker.key.urlsafe())
                for session in sessions:
                    items.append(self._copySessionToForm(session, conf))
        return SessionForms(items=items)


    @endpoints.method(SESSION_GET_BY_KEY, BooleanMessage, path='sessions/addToWishList/{sessionKey}',
                      http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        prof = self._getProfileFromUser()
        session = ndb.Key(urlsafe=request.sessionKey).get()
        # print "the session's parent is: ", session.parent
        if not session:
            raise endpoints.NotFoundException('No session with that key: %s' % request.sessionKey)
            return BooleanMessage(data=False)
        if request.sessionKey in prof.session_wish_list:
                raise ConflictException(
                    "You have already expressed your desire to be at this session!")
        else:
            prof.session_wish_list.append(request.sessionKey)
            prof.put()
        return BooleanMessage(data=True)


    @endpoints.method(SESSION_GET_BY_WISHLIST, SessionForms, 
            path='conference/{websafeConferenceKey}/sessions/users/wishlist', http_method='GET', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """ Return all the sessions a user is going to attend in a conference. """
        profile = self._getProfileFromUser()
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException('No conference with that key: %s', request.websafeConferenceKey)
        sessions = Session.query(ancestor=conf.key)
        items = []
        for session in sessions:
            if session.key.urlsafe() in profile.session_wish_list:
                items.append(self._copySessionToForm(session, conf))
        return SessionForms(items=items)


    @endpoints.method(SessionForm, SessionForm, path='sessions',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create new conference."""
        return self._createSessionObject(request)

    def _createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Session 'name' field required")
        if not request.speaker_email:
            raise endpoints.BadRequestException("Session 'speaker_email' field required")
        if not request.date:
            raise endpoints.BadRequestException("Session 'date' field required")
        if not request.start_time:
            raise endpoints.BadRequestException("Session 'start time' field required")

        # Let's get the conference object from the websafe key, as entered by the user
        wsck = request.conf_websafekey
        conf = ndb.Key(urlsafe=wsck).get()
        # print "The conf key is : ", conf.key()

        # Let's get the speaker, as per the email address that user entered
        # check if speaker object exists:
        speaker_key = ndb.Key(Speaker, request.speaker_email)
        speaker = speaker_key.get()
        # if speaker object does not exist, check if the speaker has a user profile already
        if not speaker:
            sp_key = ndb.Key(Profile, request.speaker_email)
            speaker_profile = sp_key.get()
            # If the speaker doesn't have a user profile yet
            if not speaker_profile:
                sp_key_urlsafe = ""
            else:
                sp_key_urlsafe = sp_key.urlsafe()
            speaker = Speaker(key=speaker_key,
                              name=request.speaker_name,
                              email=request.speaker_email,
                              user_profile_key=sp_key_urlsafe)
            speaker.put()
        speaker_key = speaker.key.urlsafe()

        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)
        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['conf_websafekey']
        del data['sess_websafekey']
        del data['speaker_email']
        del data['speaker_name']

        # Once we have a speaker, we can put the key 
        data['speaker_key'] = speaker_key

        data['type_of_session'] = str(data['type_of_session'])
        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS_SESSION:
            if data[df] in (None, []):
                data[df] = DEFAULTS_SESSION[df]
                setattr(request, df, DEFAULTS_SESSION[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['date']:
            data['date'] = datetime.strptime(data['date'][:10], "%Y-%m-%d")
        if data['start_time']:
            data['start_time'] = datetime.strptime(data['start_time'][:10], "%H:%M")

        # The following code makes the session a child of the conference
        # Get the Key instance form the urlsafe key
        c_key = ndb.Key(urlsafe=wsck)
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key
        sess = Session(**data)
        sess.put()
        # Count how many sessions the speaker is to speak in.
        speakers_count = Session.query(ancestor=conf.key).filter(Session.speaker_key == sess.speaker_key).count()
        taskqueue.add(params={'speaker': speaker.name, 'count': speakers_count},
            url='/tasks/set_featured_speaker'
        )
        return request


    def _getSessionsQuery(self, inequality_field, filter_set, conf_key):
        """ Return formatted query from the submitted filters for Sessions."""
        s = Session.query(ancestor=conf_key)
        print "This is what one filter set looks like: ", filter_set
        if not inequality_field:
            s = s.order(Session.name)
        else:
            s = s.order(ndb.GenericProperty(inequality_field))
            s = s.order(Session.name)
        print "Here is the filter set in sessionsQuery ", filter_set
        for filtr in filter_set:
            if filtr["field"] == "start_time":
                print "this is the value: ", filtr["value"]
                value = datetime.strptime(filtr["value"][:10], "%H:%M")
                print "Formatting the start time field: ", value
            elif filtr["field"] == "date":
                value = datetime.strptime(filtr["value"][:10], "%Y-%m-%d")
                print "Formatting the date: ", filtr["value"]
            elif filtr["field"] == "duration":
                value = int(filtr["value"])
            else:
                value = filtr["value"]
                print "Post formatting, the filters are: ", filtr
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], value)
            s = s.filter(formatted_query)
            print "the first filters results: ", s
        return s

    def _getExtraInequalityFiltering(self, filters, session_list):
        processed_session_list = []
        print "These are the extra inq filters: ", filters
        for filtr in filters:
            for session in session_list:
                print "The session is: ", session.name
                if filtr["field"] == "start_time":
                    value = datetime.strptime(filtr["value"], "%H:%M").time()
                    if filtr["operator"] == '>':
                        if session.start_time > value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '>=':
                        if session.start_time >= value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<':
                        if session.start_time < value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<=':
                        if session.start_time <= value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '!=':
                        if session.start_time != value:
                            processed_session_list.append(session)
                elif filtr["field"] == "date":
                    value = datetime.strptime(filtr["value"], "%Y-%m-%d").date()
                    if filtr["operator"] == '>':
                        if session.date > value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '>=':
                        if session.date >= value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<':
                        if session.date < value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<=':
                        if session.date <= value:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '!=':
                        if session.date != value:
                            processed_session_list.append(session)
                elif filtr["field"] == "duration":
                    print "The duration filter is: ", filtr['value'], filtr['operator']
                    filtr["value"] = int(filtr["value"])
                    if filtr["operator"] == '>':
                        print "The session's duration is: ", session.duration
                        print "Yes the duration is greater than ", filtr['value']
                        if session.duration > filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '>=':
                        if session.duration >= filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<':
                        if session.duration < filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<=':
                        if session.duration <= filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '!=':
                        if session.duration != filtr["value"]:
                            processed_session_list.append(session)
                elif filtr["field"] == "type_of_session":
                    # filtr["value"] = datetime.strptime(filtr["value"], "%Y-%m-%d")
                    if filtr["operator"] == '>':
                        if session.type_of_session > filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '>=':
                        if session.type_of_session >= filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<':
                        if session.type_of_session < filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '<=':
                        if session.type_of_session <= filtr["value"]:
                            processed_session_list.append(session)
                    elif filtr["operator"] == '!=':
                        if session.type_of_session != filtr["value"]:
                            processed_session_list.append(session)
            # after each filter is processed, reset the lists
            session_list = processed_session_list
            processed_session_list = []
        return session_list


    @endpoints.method(SessionQueryForms, SessionForms,
            path='querySessions',
            http_method='POST',
            name='querySessions')
    def querySessions(self, request):
        print "We are in query sessions"
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException('No conference exists with key: %s' % request.websafeConferenceKey)
        # sessions = Session.query(ancestor=conf.key)
        print "got the conf"
        inequality_field, filters, extra_inequality_filters = self._formatFilters(request.filters, 'sess')
        print "Got the filters: ", filters
        sessions_list = []
        sessions = self._getSessionsQuery(inequality_field, filters, conf.key)
        # Get the sessions objects
        print "We are out of the first query"
        print "the sessions query as returned: ", sessions
        for session in sessions:
            print "The session's startimes in the first result: ", session.start_time
            sessions_list.append(session)

        sessions_list = self._getExtraInequalityFiltering(extra_inequality_filters, sessions_list)
        return SessionForms(
            items=[self._copySessionToForm(session, conf) for session in sessions_list]
        )

api = endpoints.api_server([ConferenceApi]) # register API
