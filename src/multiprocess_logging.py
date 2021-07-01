# vim : fileencoding=UTF-8 :

from __future__ import absolute_import, division, unicode_literals

import multiprocessing
import sys
import os
import threading
import traceback
import queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../', 'lib/'))
import logger as logging

__version__ = '0.3.1'


def install_mp_handler(logger=None):
	"""Wraps the handlers in the given Logger with an MultiProcessingHandler.

    :param logger: whose handlers to wrap. By default, the root logger.
    """
	if logger is None:
		logger = logging.getLogger()

	for i, orig_handler in enumerate(list(logger.handlers)):
		handler = MultiProcessingHandler(
			'mp-handler-{0}'.format(i), sub_handler=orig_handler)

		logger.removeHandler(orig_handler)
		logger.addHandler(handler)


def uninstall_mp_handler(logger=None):
	"""Unwraps the handlers in the given Logger from a MultiProcessingHandler wrapper

    :param logger: whose handlers to unwrap. By default, the root logger.
    """
	if logger is None:
		logger = logging.getLogger()

	for handler in logger.handlers:
		if isinstance(handler, MultiProcessingHandler):
			orig_handler = handler.sub_handler
			logger.removeHandler(handler)
			logger.addHandler(orig_handler)


class MultiProcessingHandler(logging.logging.Handler):

	def __init__(self, name, sub_handler=None):
		super(MultiProcessingHandler, self).__init__()

		if sub_handler is None:
			sub_handler = logging.logging.StreamHandler()
		self.sub_handler = sub_handler

		self.setLevel(self.sub_handler.level)
		self.setFormatter(self.sub_handler.formatter)
		self.filters = self.sub_handler.filters

		self.queue = multiprocessing.Queue(-1)
		self._is_closed = False
		# The thread handles receiving records asynchronously.
		self._receive_thread = threading.Thread(target=self._receive, name=name)
		self._receive_thread.daemon = True
		self._receive_thread.start()

	def setLevel(self, level):
		"""
	setLevel: sets the verbosity level of the logger
	@param: level	verbosity level setting
	"""
		try:
			super(MultiProcessingHandler, self).setLevel(logging.MAX - int(level) + 1)
		except:
			super(MultiProcessingHandler, self).setLevel(level.upper())

	def setFormatter(self, fmt):
		super(MultiProcessingHandler, self).setFormatter(fmt)
		self.sub_handler.setFormatter(fmt)

	def _receive(self):
		while True:
			try:
				if self._is_closed and self.queue.empty():
					break

				record = self.queue.get(timeout=0.2)
				self.sub_handler.emit(record)
			except (KeyboardInterrupt, SystemExit):
				raise
			except (BrokenPipeError, EOFError):
				break
			except queue.Empty:
				pass  # This periodically checks if the logger is closed.
			except:
				traceback.print_exc(file=sys.stderr)

		self.queue.close()
		self.queue.join_thread()

	def _send(self, s):
		self.queue.put_nowait(s)

	def _format_record(self, record):
		# ensure that exc_info and args
		# have been stringified. Removes any chance of
		# unpickleable things inside and possibly reduces
		# message size sent over the pipe.
		if record.args:
			record.msg = record.msg % record.args
			record.args = None
		if record.exc_info:
			self.format(record)
			record.exc_info = None

		return record

	def emit(self, record):
		try:
			s = self._format_record(record)
			self._send(s)
		except (KeyboardInterrupt, SystemExit):
			raise
		except:
			self.handleError(record)

	def close(self):
		if not self._is_closed:
			self._is_closed = True
			self._receive_thread.join(5.0)  # Waits for receive queue to empty.

			self.sub_handler.close()
			super(MultiProcessingHandler, self).close()
