# Minihorse
Simple CMS-like web service for managing "Art Battles" at tabun.everypony.ru
* Generates drafts or publishes posts.
* Stores each date's Art Battle information and participants' artworks.
* Parses incoming email notifications from tabun.everypony.ru and automatically adds new participants to the current Art Battle.

Requires Google App Engine Python SDK. Get it here: https://cloud.google.com/appengine/downloads

If you wish to upload the app to your own App Engine project, you will need a separate `app.yaml` config with your own app ID.
