"""Integration with nest devices."""

import json
import logging
import time
import urllib2
import uuid

from google.appengine.ext import ndb

import flask

from appengine import model, rest, user


REDIRECT_URL = 'https://homeawesomation.appspot.com/api/account/redirect'
ACCOUNT_TYPES = {}


def register(account_type):
  """Decorator to cause accounts types to be registered."""
  def class_rebuilder(cls):
    ACCOUNT_TYPES[account_type] = cls
    return cls
  return class_rebuilder


class Account(model.Base):
  """Class represents an account."""
  CLIENT_ID = None
  CLIENT_SECRET = None
  ACCESS_TOKEN_URL = None
  AUTH_URL = None

  auth_code = ndb.StringProperty(required=False)
  access_token = ndb.StringProperty(required=False)
  expires = ndb.FloatProperty(required=False)
  refresh_token = ndb.StringProperty(required=False)

  owner = ndb.StringProperty(required=True)
  human_type = ndb.ComputedProperty(lambda a: a.get_human_type())
  last_update = ndb.DateTimeProperty(required=False, auto_now=True)

  @classmethod
  def _event_classname(cls):
    return 'account'

  def get_human_type(self):
    return ''

  def _get_refresh_data(self):
    return ''

  @rest.command
  def refresh_access_token(self):
    """For a given account, refresh the access token."""
    parameters = {'client_id': self.CLIENT_ID,
                  'auth_code': self.auth_code,
                  'client_secret': self.CLIENT_SECRET,
                  'grant_type': 'authorization_code'}
    url = self.ACCESS_TOKEN_URL % parameters
    data = self._get_refresh_data()
    logging.info('url: %s, data: %s', url, data)

    try:
      # empty data to trigger a post
      result = urllib2.urlopen(url, data)
      result = json.load(result)
      logging.info('result: %s', result)
    except urllib2.HTTPError, err:
      result = json.load(err)
      logging.info(result)
      raise err

    self.access_token = result['access_token']
    self.expires = time.time() + result['expires_in']
    self.refresh_token = result.get('refresh_token', None)

  @rest.command
  def refresh_devices(self):
    pass


# pylint: disable=invalid-name
blueprint = flask.Blueprint('account', __name__)
rest.register_class(blueprint, Account, None)


@blueprint.route('/start_flow')
def oauth_start_flow():
  """Step 1; Beginning of oauth account flow.

  UI will open this page; we create an accounts objects
  and redirect to appropriate server.  We use account
  id as random string for oauth flow.
  """
  account_type = flask.request.args.get('type')
  if account_type is None:
    flask.abort(400)

  cls = ACCOUNT_TYPES.get(account_type, None)
  if cls is None:
    flask.about(400)

  key = str(uuid.uuid4())
  instance = cls(id=key, owner=user.get_user())
  instance.put()

  return flask.redirect(instance.AUTH_URL %
                        {'client_id': cls.CLIENT_ID,
                         'state': key})


@blueprint.route('/redirect')
def oauth_redirect_callback():
  """Step 2: Nest (etc) server redirects back to us
  with an auth_code - use this refresh access token.
  """
  auth_code = flask.request.args.get('code', None)
  state = flask.request.args.get('state', None)
  if auth_code is None or state is None:
    logging.info('No auth_code of state found!')
    flask.abort(400)

  account = Account.get_by_id(state)
  if account is None:
    logging.info('Account \'%s\' not found!', state)
    flask.abort(400)

  account.auth_code = auth_code
  account.refresh_access_token()
  account.refresh_devices()
  account.put()

  return "OK"
