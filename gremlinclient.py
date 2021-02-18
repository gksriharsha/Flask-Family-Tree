# from tornado import gen
# from tornado.ioloop import IOLoop
# from gremlinclient.tornado_client import submit
#
# loop = IOLoop.current()
#
#  @gen.coroutine
#  def go():
#      resp = yield submit("ws://localhost:8182/", "1 + 1")
#      while True:
#          msg = yield resp.read()
#          if msg is None:
#              break
#          print(msg)
#  loop.run_sync(go)