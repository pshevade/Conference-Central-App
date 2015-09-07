Conference Central Application

App Engine application for the Udacity training course.

https://learning-project-2015.appspot.com/_ah/api/explorer


CONFERENCE CENTERAL API ENDPOINTS:

Conference
1.  createConference - Create a conference 
2.  registerForConference - register (as logged in user) for a particular conference
3.  unregisterFromConference - unregister (as logged in user) from a 
    particular conference
4.  getConference - get a conference by websafekey
5.  getConferencesCreated - get all conferences created by the logged in user
6.  getConferencesToAttend - get all conferences that the user plans to attend
7.  updateConference - Update conference w/ provided fields and return 
    with updated info

Session
8.  createSession - create a session for a particular conference
9.  addSessionToWishlist - add the session to the user's wishlist
10. getConferenceSessions - get sessions for a particular conference
11. getConferenceSessionsByDate - get all sessions on a date for a 
    particular conference
12. getConferenceSessionsByType - get all sessions of a type for a conference
13. getSessionsBySpeaker - get all sessions that features this speaker across 
    all conference
14. getSessionsInWishlist - get all sessions the user is planning to attend 
    (as per wishlist) in a conference 

User
15. getProfile - return user profile
16. saveProfile - update and return user profile 
17. getProfilesBySessionWishlist - return all profiles who have a particular 
    session in their wishlists
18. getFeaturedSpeaker - get the featured speaker 

Query
19. queryConferences - pass filters to perform a generic selection on conferences
20. querySessions - pass filters to perform a generic selection on sessions 
    (NOTE: you can pass multiple inequality filters to this query. See below for more info.)


WHAT ARE THE REQUIREMENTS:
1. Products
- [Google App Engine][1] 

2. Languages
- [Python v 2.7+][2] 
3. APIs
- [Google Cloud Endpoints][3]


SETUP INSTRUCTIONS:
To run a copy locally - 
0. Make sure requirements are up to date. 
1. Register an App ID in the [App Engine admin console][4]
2. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
3. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
4. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
5. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
6. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
7. (Optional) Generate your client library(ies) with [the endpoints tool][6].
8. Deploy your application.
9. When you go to [localhost:8080][5] (or wherever you have hosted), to view the API explorer add /_ah/api/explorer to the path to view the API Explorer. You may have to click on the silver shield that appears in the right corner of the address bar of the browser and select ["Load unsafe scripts"][7] (as per the message in the red banner at top of page). None of these HTTPS issues apply since you are running the APIs Explorer locally in a test environment



DESIGN CHOICES: (Task 1)

  1. Session Class

- The Session class has the ancestor Conference. This will make sure that a session
  can only belong to one conference. Also, you can find all sessions for a conference by performing a query by ancestor.

- The session has a "start_time" property - which is a DateTimeProperty in which we 
  only populate the time. The session has a "date" property - which is a DateTimeProperty in which we only populate the date. Alternatively we can store these as TimeProperty and DateProperty respectively, but this was causing problems with querying. 

- The session also has a "speaker_key" StringProperty - this holds the urlsafe key 
  to the speaker that is associated with the session.


  2. Speaker Class

- The Speaker class is created to hold details about the speaker. One option was to
  just have a string in the Session class that holds the speaker's name. But this wasn't sufficient. 

- The Speaker has the name, email, and speciality properties as placeholders. 

- The name property is used to find all sessions where the speaker is presenting 
  (used in APIs Endpoints: getSessionsBySpeaker, getSessionsInWishlist, getProfilesBySessionWishlist,getFeaturedSpeaker)

- The email property is used to find the user profile associated with this speaker. 
  The speaker is also an attendee of the conferences, so it can be beneficial to have the user profile tied to the Speaker class. So we store the urlsafe key to the userprofile corresponding to that email address (if that user/speaker has registered in our Conference Central App). 

- The speciality property is just an extra piece of information about the Speaker.



DESIGN CHOICES (Task 3):

Additional 2 queries:
1. getProfilesBySessionWishlist 
   - This endpoint returns all user profiles who share a particular session in their wishlist.
2. getConferenceSessionsByDate
   - This endpoint returns all the session that occur on a particular date for a given conference.



QUERY RELATED PROBLEM (Task 3):

Datastore rejects inequality filtering on more than one property at a time.
I solved this by performing the first inequality filtering using the ndb filternode 
(using the _getSessionsQuery() function) and then building the remaining inequality filters separately using the _getExtraInequalityFiltering() function) 

You can perform multiple inequality filtering using the querySessions endpoint.


TODOS: 

1. Make sure that session dates lie between conferences dates
2. Make sure that session times do not overlap
3. 

[1]: https://developers.google.com/appengine
[2]: https://www.python.org/download/releases/2.7.6/
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
[7]: https://cloud.google.com/appengine/docs/python/endpoints/test_deploy
