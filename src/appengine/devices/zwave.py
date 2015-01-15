"""Generic Z Wave device driver."""

import logging

from google.appengine.ext import ndb

from appengine import device, pushrpc, rest, room


ZWAVE_DRIVERS = {}


class Driver(object):
  """A manufacture / product specific driver for a zwave device.

  NB has to be stateless.  Store you state in the zwave devices.
  """

  def __init__(self, _device):
    self._device = _device

  def get_capabilities(self):
    return []

  def _send_device_command(self, command, **kwargs):
    """Convenience method to send a command to this device."""
    event = {'type': 'zwave',
             'command': command,
             'node_id': self._device.zwave_node_id}
    event.update(kwargs)
    pushrpc.send_event(event)


def register(manufacturer_id, product_type, product_id):
  """Decorator to cause device types to be registered."""
  key = '%s-%s-%s' % (manufacturer_id, product_type, product_id)
  def class_rebuilder(cls):
    ZWAVE_DRIVERS[key] = cls
    return cls
  return class_rebuilder


def get_driver(manufacturer_id, product_type, product_id):
  key = '%s-%s-%s' % (manufacturer_id, product_type, product_id)
  return ZWAVE_DRIVERS.get(key, Driver)


class CommandClassValue(ndb.Model):
  """A particular (command class, value)."""

  command_class = ndb.StringProperty()
  index = ndb.IntegerProperty()
  value = ndb.GenericProperty()
  read_only = ndb.BooleanProperty()
  units = ndb.StringProperty()
  genre = ndb.StringProperty()
  label = ndb.StringProperty()
  value_id = ndb.IntegerProperty()
  type = ndb.StringProperty()


@device.register('zwave')
class ZWaveDevice(device.Device):
  """Generic Z Wave device driver."""
  # pylint: disable=too-many-instance-attributes
  zwave_node_id = ndb.IntegerProperty(required=False)
  zwave_home_id = ndb.IntegerProperty(required=False)
  zwave_command_class_values = ndb.StructuredProperty(
      CommandClassValue, repeated=True)

  zwave_node_type = ndb.StringProperty()
  zwave_node_name = ndb.StringProperty()
  zwave_manufacturer_name = ndb.StringProperty()
  zwave_manufacturer_id = ndb.StringProperty()
  zwave_product_name = ndb.StringProperty()
  zwave_product_type = ndb.StringProperty()
  zwave_product_id = ndb.StringProperty()

  # Haven't found a good way to fake out the properites yet
  state = ndb.BooleanProperty()

  def __init__(self, **kwargs):
    super(ZWaveDevice, self).__init__(**kwargs)
    self._driver = None

  @property
  def driver(self):
    """Find the zwave driver for this device."""
    if self._driver is not None:
      return self._driver

    key = '%s-%s-%s' % (self.zwave_manufacturer_id,
                        self.zwave_product_type,
                        self.zwave_product_id)
    _driver = ZWAVE_DRIVERS.get(key, None)
    logging.info('ZWave driver for %s = %s', key,
                 _driver.__name__)

    if _driver is None:
      return Driver(self)
    else:
      self._driver = _driver(self)
      return self._driver

  # This is a trampoline through to the driver
  # as this class cannot impolement everything
  def __getattr__(self, name):
    return getattr(self.driver, name)

  def get_capabilities(self):
    return self.driver.get_capabilities()

  def _command_class_value(self, command_class, index):
    """Find the given (command_class, index) or create a new one."""
    for ccv in self.zwave_command_class_values:
      if ccv.command_class == command_class and ccv.index == index:
        return ccv
    ccv = CommandClassValue(command_class=command_class, index=index)
    self.zwave_command_class_values.append(ccv)
    return ccv

  def handle_event(self, event):
    """Handle an event form the zwave device."""
    super(ZWaveDevice, self).handle_event(event)

    notification_type = event['notificationType']
    if 'homeId' in event:
      self.zwave_home_id = event['homeId']
    if 'nodeId' in event:
      self.zwave_node_id = event['nodeId']

    if notification_type in {'ValueAdded', 'ValueChanged'}:
      value = event['valueId']
      command_class = value.pop('commandClass')
      index = value.pop('index')
      value['read_only'] = value.pop('readOnly')
      value['value_id'] = value.pop('id')
      del value['homeId']
      del value['nodeId']
      del value['instance']

      ccv = self._command_class_value(command_class, index)
      ccv.populate(**value)

      logging.info('%s.%s[%d] <- %s', self.zwave_node_id,
                   command_class, index, value)

      if command_class == 'COMMAND_CLASS_SENSOR_BINARY':
        self.lights(value['value'])

    elif notification_type == 'NodeInfoUpdate':
      # event['basic']
      # event['generic']
      # event['specific']
      self.zwave_node_type = event['node_type']
      self.zwave_node_name = event['node_name']
      self.zwave_manufacturer_name = event['manufacturer_name']
      self.zwave_manufacturer_id = event['manufacturer_id']
      self.zwave_product_name = event['product_name']
      self.zwave_product_type = event['product_type']
      self.zwave_product_id = event['product_id']

    else:
      logging.info("Unknown event: %s", event)

  @rest.command
  def lights(self, state):
    """Turn the lights on/off in the room this sensor is in."""
    if not self.room:
      return

    room_obj = room.Room.get_by_id(self.room)
    if not room_obj:
      return

    room_obj.set_lights(state)

  @classmethod
  @device.static_command
  def heal(cls):
    event = {'type': 'zwave', 'command': 'heal'}
    pushrpc.send_event(event)

  @rest.command
  def heal_node(self):
    event = {'type': 'zwave', 'command': 'heal_node',
             'node_id': self.zwave_node_id}
    pushrpc.send_event(event)
