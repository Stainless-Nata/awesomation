"""Base classes for my data model."""

import logging

from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel

import flask


class Base(polymodel.PolyModel):

  def to_dict(self):
    """Convert this object to a python dict."""
    result = super(Base, self).to_dict()
    result['id'] = self.key.id()
    result['class'] = result['class_'][-1]
    del result['class_']
    return result


class Person(Base):
  # key_name is userid
  email = ndb.StringProperty(required=False)


class Account(Base):
  owner = ndb.StringProperty(required=True)
  oauth_state = ndb.StringProperty(required=False)
  oauth_access_token = ndb.StringProperty(required=False)
  oauth_refresh_token = ndb.StringProperty(required=False)


class Room(Base):
  """A room in a property."""
  owner = ndb.StringProperty(required=True)
  name = ndb.StringProperty(required=False)
  devices = ndb.KeyProperty(repeated=True)


def Command(func):
  """Device command decorator - automatically dispatches methods."""
  func.is_command = True
  return func


class Device(Base):
  """Base class for all device drivers."""
  owner = ndb.StringProperty(required=True)
  name = ndb.StringProperty(required=False)
  last_update = ndb.DateTimeProperty(required=False, auto_now=True)
  room = ndb.KeyProperty()

  def handle_event(self, event):
    pass

  def handle_command(self, command):
    """Dispatch command to appropriate handler."""
    logging.info(command)
    func_name = command.pop('command', None)
    func = getattr(self, func_name, None)
    if func is None or not func.is_command:
      logging.error('Command %s does not exist or is not a command',
                    func_name)
      flask.abort(400)
    func(**command)

  @Command
  def set_room(self, room_id):
    """Change the room associated with this device."""
    room = Room.get_by_id(room_id)
    if not room:
      flask.abort(404)
    room.devices.append(self.key)
    room.put()

    self.room = room.key
    self.put()


class Switch(Device):
  """A swtich."""
  state = ndb.BooleanProperty()

  @Command
  def turn_on(self):
    pass

  @Command
  def turn_off(self):
    pass
