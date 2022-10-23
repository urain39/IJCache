'''Implements base caches.
'''


import abc
import marshal
import random


# Unique object to instead None
VOID = object()


class Item(abc.ABC):
  '''The item wrapper interface. It supports custom event handlers.

  :param value: Item value
  :type value: any
  '''
  def __init__(self, value):
    self.value = value

  @abc.abstractmethod
  def on_hit(self):
    '''A callback for event hit.
    '''

  @abc.abstractmethod
  def on_evict(self):
    '''A callback for event evict.
    '''


class Cache(abc.ABC):
  '''The cache interface.

  :param size: The cache size
  :type size: int, optional
  '''

  VOID = VOID

  def __init__(self, size=32):
    self._size = size
    self._map = {}

  @abc.abstractmethod
  def add(self, key, value):
    '''Adds an item into cache. If item is an :class:`Item`, then
    implementations should manually call :meth:`Item.on_evict` before evicting.

    :param key: The cache key
    :type key: str
    :param value: The cache value
    :type value: any
    '''

  @abc.abstractmethod
  def remove(self, key):
    '''Removes an item in cache. If item is an :class:`Item`, then
    implementations should manually call :meth:`Item.on_evict` before removing.

    :param key: The cache key
    :type key: str
    '''

  def clear(self):
    '''Clear all items in cache.
    '''
    keys = tuple(self._map.keys())
    for k in keys:
      self.remove(k)

  @abc.abstractmethod
  def lookup(self, key):
    '''Lookups an item in cache. If item is an :class:`Item`, then
    implementations should manually call :meth:`Item.on_hit` before return.

    :param key: The cache key
    :type key: str
    :return: The cache value
    :rtype: any or `Cache.VOID`
    '''

  def ensure(self, key, lazy):
    '''Equals lookup() + add(). If lookup() cache missed, then adds a value from
    lazy(), and returns the value.

    :param key: The cache key
    :type key: str
    :param lazy: A function to build new value (any)
    :type lazy: function
    :return: The cache value
    :rtype: any
    '''
    # pylint: disable=invalid-name
    v = self.lookup(key)
    if v == VOID:
      v = lazy()
      self.add(key, v)
    return v
    # pylint: enable=invalid-name

  # pylint: disable=invalid-name
  def cache(self, fn):
    '''A decorator like `functools.lru_cache`. May be very slow, due to too
    many wrappings.

    :param fn: A function to cache results
    :type fn: function
    :return: A wrapped function
    :rtype: function
    '''
    def wrapped(*args, **kwargs):
      return self.ensure(marshal.dumps((args, kwargs)),
        lambda : fn(*args, **kwargs))
    return wrapped
  # pylint: enable=invalid-name


class LRUCache(Cache):
  '''The least-recently-used cache. Better when you want real LRU. Size limited in 1-1024.

  :param size: The cache size
  :type size: int, optional
  '''
  def __init__(self, size=32):
    assert 1 <= size <= 1024
    super().__init__(size)
    self._head = None
    self._tail = None

  def add(self, key, value):
    '''Adds an item into cache.

    :param key: The cache key
    :type key: str
    :param value: The cache value
    :type value: any
    '''
    # pylint: disable=invalid-name
    tail = self._tail
    map_ = self._map
    assert key not in map_
    # If size reached max, replace tail one instead
    if len(map_) >= self._size:
      v = tail[1]
      if isinstance(v, Item):
        v.on_evict()
      # Delete oldest one's key in map
      del map_[tail[0]]
      # In-place replace with new one
      tail[0] = key
      tail[1] = value
      map_[key] = tail
    else:
      head = self._head
      if head == None or tail == None:
        head = [key, value, None, None]
        self._head = head
        self._tail = head
        map_[key] = head
        return
      c = [key, value, tail, None]
      tail[3] = c
      self._tail = c
      map_[key] = c
    # pylint: enable=invalid-name

  def remove(self, key):
    '''Removes an item in cache.

    :param key: The cache key
    :type key: str
    '''
    # pylint: disable=invalid-name
    map_ = self._map
    c = map_.get(key)
    if c != VOID:
      v = c[1]
      if isinstance(v, Item):
        v.on_evict()
      del map_[c[0]]
      head = self._head
      tail = self._tail
      if c == head:
        if c == tail:
          self._head = None
          self._tail = None
          return
        n = c[3]
        n[2] = None
        self._head = n
        return
      if c == tail:
        p = c[2]
        p[3] = None
        self._tail = p
        return
      p = c[2]
      n = c[3]
      p[3] = n
      n[2] = p
    # pylint: enable=invalid-name

  # pylint: disable-next=inconsistent-return-statements
  def lookup(self, key):
    '''Lookups an item in cache.

    :param key: The cache key
    :type key: str
    :return: The cache value
    :rtype: any or `Cache.VOID`
    '''
    # pylint: disable=invalid-name
    c = self._map.get(key, VOID)
    # pylint: disable-next=multiple-statements
    if c == VOID: return VOID
    v = c[1]
    if isinstance(v, Item):
      v.on_hit()
    # Make c be first of cache
    head = self._head
    # pylint: disable-next=multiple-statements
    if c == head: return v
    p = c[2]
    # Remove
    if c == self._tail:
      p[3] = None
      self._tail = p
    else:
      n = c[3]
      p[3] = n
      n[2] = p
    # Insert
    head[2] = c
    c[3] = head
    c[2] = None  # Keep head previous reference always be None
    self._head = c
    return v
    # pylint: enable=invalid-name


class TRCCache(Cache):
  '''The 2-random choices cache. Better when less cache misses. Size limited in
  2-1024.

  :param size: The cache size
  :type size: int, optional
  '''
  def __init__(self, size=32):
    assert 2 <= size <= 1024
    super().__init__(size + 1 if size & 1 else size)
    self._tick = 0
    self._cache = []

  def add(self, key, value):
    '''Adds an item into cache.

    :param key: The cache key
    :type key: str
    :param value: The cache value
    :type value: any
    '''
    # pylint: disable=invalid-name
    cache = self._cache
    map_ = self._map
    assert key not in map_
    c = [key, value, 0]
    l = len(cache)
    # If size reached max, replace an old one instead
    if l >= self._size:
      # 2-random choices; Assume first is older one
      h = l >> 1  # Make co != c2
      i = random.randrange(0, h)
      co = cache[i]
      c2 = cache[h + i]
      # Always store older one to co
      # pylint: disable-next=multiple-statements
      if c2[2] < co[2]: co = c2
      v = co[1]
      if isinstance(v, Item):
        v.on_evict()
      # Delete older one's key in map
      k = co[0]
      # pylint: disable-next=multiple-statements
      if k != None: del map_[k]
      # In-place replace with new one
      co.clear()
      co.extend(c)
      map_[key] = co
    else:
      cache.append(c)
      map_[key] = c
    # pylint: enable=invalid-name

  def remove(self, key):
    '''Removes an item in cache.

    :param key: The cache key
    :type key: str
    '''
    # pylint: disable=invalid-name
    map_ = self._map
    c = map_.get(key)
    if c != VOID:
      v = c[1]
      if isinstance(v, Item):
        v.on_evict()
      del map_[c[0]]
      c[0] = None
      c[1] = None
      c[2] = 0
    # pylint: enable=invalid-name

  # pylint: disable-next=inconsistent-return-statements
  def lookup(self, key):
    '''Lookups an item in cache.

    :param key: The cache key
    :type key: str
    :return: The cache value
    :rtype: any or `Cache.VOID`
    '''
    # pylint: disable=invalid-name
    c = self._map.get(key, VOID)
    # pylint: disable-next=multiple-statements
    if c == VOID: return VOID
    v = c[1]
    if isinstance(v, Item):
      v.on_hit()
    # Only update tick when needed
    self._tick += 1
    c[2] = self._tick
    return c[1]
    # pylint: enable=invalid-name


class LMCache(Cache):
  '''The lucky-monkey cache. Like reduced LRU cache. Fast and unsafe. Size
  limited in 1-256. Not removable.

  :param size: The cache size
  :type size: int, optional
  '''
  def __init__(self, size=32):
    assert 1 <= size <= 256
    super().__init__(size)
    self._cache = []

  def add(self, key, value):
    '''Adds an item into cache.

    :param key: The cache key
    :type key: str
    :param value: The cache value
    :type value: any
    '''
    # pylint: disable=invalid-name
    cache = self._cache
    map_ = self._map
    assert key not in map_
    l = len(cache)
    # If size reached max, replace an old one instead
    if l >= self._size:
      # Always assume tail one is old one
      co = cache[l - 1]
      v = co[1]
      if isinstance(v, Item):
        v.on_evict()
      # Delete old one's key in map
      del map_[co[0]]
      # In-place replace with new one
      co[0] = key
      co[1] = value
      map_[key] = co
    else:
      c = [key, value, l]
      cache.append(c)
      map_[key] = c
    # pylint: enable=invalid-name

  def remove(self, key):
    '''Removes an item in cache. This method is not implemented.

    :param key: The cache key
    :type key: str
    '''
    raise NotImplementedError()

  # pylint: disable-next=inconsistent-return-statements
  def lookup(self, key):
    '''Lookups an item in cache.

    :param key: The cache key
    :type key: str
    :return: The cache value
    :rtype: any or `Cache.VOID`
    '''
    # pylint: disable=invalid-name
    c = self._map.get(key, VOID)
    # pylint: disable-next=multiple-statements
    if c == VOID: return VOID
    v = c[1]
    if isinstance(v, Item):
      v.on_hit()
    # Make c be first of cache
    i = c[2]
    # pylint: disable-next=multiple-statements
    if i == 0: return v
    # Swap cache[i] and cache[0]
    cache = self._cache
    h = cache[0]
    c[2] = 0
    cache[0] = c
    h[2] = i
    cache[i] = h
    return v
    # pylint: enable=invalid-name


class BPLRUCache(Cache):
  '''The bit-PLRU cache. Better when often cache misses? Size limited in 1-32.

  :param size: The cache size
  :type size: int, optional
  '''
  POSITION = {
    1: 0,
    2: 1,
    4: 2,
    8: 3,
    16: 4,
    32: 5,
    64: 6,
    128: 7,
    256: 8,
    512: 9,
    1024: 10,
    2048: 11,
    4096: 12,
    8192: 13,
    16384: 14,
    32768: 15,
    65536: 16,
    131072: 17,
    262144: 18,
    524288: 19,
    1048576: 20,
    2097152: 21,
    4194304: 22,
    8388608: 23,
    16777216: 24,
    33554432: 25,
    67108864: 26,
    134217728: 27,
    268435456: 28,
    536870912: 29,
    1073741824: 30,
    2147483648: 31
  }

  def __init__(self, size=32):
    assert 1 <= size <= 32
    super().__init__(size)
    self._status = 0
    self._status_max = (1 << size) - 1
    self._cache = []

  def add(self, key, value):
    '''Adds an item into cache.

    :param key: The cache key
    :type key: str
    :param value: The cache value
    :type value: any
    '''
    # pylint: disable=invalid-name
    cache = self._cache
    map_ = self._map
    assert key not in map_
    l = len(cache)
    # If size reached max, replace an old one instead
    if l >= self._size:
      status = self._status
      # Find out first unused item
      co = cache[self.POSITION[~status & (status + 1)]]
      v = co[1]
      if isinstance(v, Item):
        v.on_evict()
      # Delete older one's key in map
      k = co[0]
      # pylint: disable-next=multiple-statements
      if k != None: del map_[k]
      # In-place replace with new one
      co[0] = key
      co[1] = value
      map_[key] = co
    else:
      c = [key, value, l]
      cache.append(c)
      map_[key] = c
    # pylint: enable=invalid-name

  def remove(self, key):
    '''Removes an item in cache.

    :param key: The cache key
    :type key: str
    '''
    # pylint: disable=invalid-name
    map_ = self._map
    c = map_.get(key)
    if c != VOID:
      v = c[1]
      if isinstance(v, Item):
        v.on_evict()
      del map_[c[0]]
      c[0] = None
      c[1] = None
      self._status &= ~(1 << c[2])
    # pylint: enable=invalid-name

  # pylint: disable-next=inconsistent-return-statements
  def lookup(self, key):
    '''Lookups an item in cache.

    :param key: The cache key
    :type key: str
    :return: The cache value
    :rtype: any or `Cache.VOID`
    '''
    # pylint: disable=invalid-name
    c = self._map.get(key, VOID)
    # pylint: disable-next=multiple-statements
    if c == VOID: return VOID
    v = c[1]
    if isinstance(v, Item):
      v.on_hit()
    status = self._status
    n = (1 << c[2])
    status |= n
    # Make status always have a 0 bit
    self._status = n if status == self._status_max else status
    return c[1]
    # pylint: enable=invalid-name
