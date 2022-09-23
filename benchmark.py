import random
import time
import functools
import ijcache as cache


# pylint: disable=invalid-name,multiple-statements
caches = {
  'none': [lambda fn: fn],
  'functools': [functools.lru_cache(16)],
  'lru': [cache.LRUCache(16).cache],
  'trc': [cache.TRCCache(16).cache],
  'lm': [cache.LMCache(16).cache],
  'bplru': [cache.BPLRUCache(16).cache]
}


def fib(x):
  if x == 1: return 1
  if x == 0: return 0
  return fib(x - 1) + fib(x - 2)


def test(n):
  items = caches.items()
  values = [random.randrange(n) for _ in range(n * 3)]
  for _, c in items:
    w = c[0](fib)
    b = time.time()
    for v in values:
      r = w(v)
    e = time.time()
    c.extend((e - b, r))
  c = 0
  for k, v in sorted(items, key=lambda x: x[1][1]):
    c += 1
    print(f'{c}. {k} {v[1]}, {v[2]}')


test(32)
