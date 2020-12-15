# coding=utf-8
# ------------------------------------------------------------------------------------------------------
# TDA596 - Lab 1
# server/server.py
# Input: Node_ID total_number_of_ID
# Students: Socrates, Plato, Aristotle
# ------------------------------------------------------------------------------------------------------
import traceback
import time
import argparse
from threading import Thread
from bottle import Bottle, run, request, template
import requests
from operator import itemgetter
import copy

class Server:
	def __init__(self, host, port, node_list, node_id):
		self._host = host
		self._port = port
		self._app = Bottle()
		self._route()
		self.board = {0: "Welcome to Distributed Systems Course"}
		self.node_list = node_list
		self.node_id = node_id
		self.entry_id = 0
		self.logical_clock = 0
		self.board_add_history = [] # [[timestamp, action, entry, element_id, process_id], [timestamp, action, entry, element_id, process_id]]
		self.board_editdelete_history = [] # [[timestamp, action, entry, element_id, process_id, old_value], [timestamp, action, entry, element_id, process_id, old_value]]
		self.board_all_history = []
		self.thread_active = False

	def _route(self):
		self._app.route('/', method="GET", callback=self.index)
		self._app.route('/board', method="GET", callback=self.get_board)
		self._app.route('/board', method="POST", callback=self.client_add_received)
		self._app.route('/board/<element_id:int>/', method="POST", callback=self.client_action_received)
		self._app.route('/propagate/<action>/<element_id:int>', method="POST", callback=self.propagation_received)

	def start(self):
		self._app.run(host=self._host, port=self._port)


	# ------------------------------------------------------------------------------------------------------
	# ROOUTE FUNCTIONS
	# ------------------------------------------------------------------------------------------------------
	# GET '/'
	def index(self):
		return template('server/index.tpl', board_title='Node {}'.format(self.node_id),
						board_dict=sorted(self.board.iteritems()), members_name_string='Andreas Månsson, '
																						   'Kamil Mudy, '
																						   'Tulathorn Sripongpankul')

	# GET '/board'
	def get_board(self):
		print self.board
		return template('server/boardcontents_template.tpl', board_title='Node {}'.format(self.node_id),
						board_dict=sorted(self.board.iteritems()))

	# POST '/board'
	def client_add_received(self):
		"""Adds a new element to the board
		Called directly when a user is doing a POST request on /board"""
		try:
			new_entry = request.forms.get('entry')
			element_id = len(self.board)  # you need to generate a entry number
			self.add_new_element_to_store(element_id, new_entry)
			self.board_add_history.append([self.logical_clock, "ADD", new_entry, self.entry_id, self.node_id])
			thread = Thread(target=self.propagate_to_nodes,
							args=('/propagate/ADD/' + str(element_id),
								  {'entry': new_entry, "timestamp": self.logical_clock, 'process_id': self.node_id},
								  'POST'))
			thread.daemon = True
			thread.start()
			return '<h1>Successfully added entry</h1>'
		except Exception as e:
			print e
		return False


	# POST '/board/<element_id:int>/'
	def client_action_received(self, element_id):
		print "You receive an element"
		print "id is ", self.node_id
		try:
			# Get the entry from the HTTP body
			entry = request.forms.get('entry')

			delete_option = request.forms.get('delete')
			# 0 = modify, 1 = delete

			old_value = self.board[element_id]

			print "the delete option is ", delete_option
			# call either delete or modify
			if delete_option == '0':
				self.modify_element_in_store(element_id, entry)
				propagate_action = 'MODIFY'

			elif delete_option == '1':
				print 'Element id is: ', element_id
				self.delete_element_from_store(element_id)
				propagate_action = 'DELETE'
			else:
				raise Exception("Unaccepted delete option")

			print propagate_action
			self.board_editdelete_history.append([self.logical_clock, propagate_action, entry, element_id, self.node_id, old_value])
			# propage to other nodes
			thread = Thread(target=self.propagate_to_nodes,
							args=('/propagate/' + propagate_action + '/' + str(element_id),
								  {'entry': entry, 'timestamp': self.logical_clock, 'process_id': self.node_id, 'old_value': old_value},
								  'POST'))
			thread.daemon = True
			thread.start()
			return '<h1>Successfully ' + propagate_action + ' entry</h1>'
		except Exception as e:
			print e
		return False


	# With this function you handle requests from other nodes like add modify or delete
	# POST '/propagate/<action>/<element_id:int>'
	def propagation_received(self, action, element_id):
		# get entry from http body
		entry = request.forms.get('entry')
		timestamp = request.forms.get('timestamp')
		process_id = request.forms.get('process_id')
		print "the action is", action
		self.increase_logical_timer(timestamp)
		if(not self.thread_active):
			self.thread_active = True
			thread = Thread(target=self.sort_board,
					args=())
			thread.daemon = True
			thread.start()
		# Handle requests
		if action == 'ADD':
			# Add the board entry
			self.board_add_history.append([int(timestamp), action, entry, element_id, int(process_id)])
			self.add_new_element_to_store(element_id, entry)
		elif action == 'MODIFY':
			# Modify the board entry
			old_value = request.forms.get('old_value')
			self.board_editdelete_history.append([int(timestamp), action, entry, element_id, int(process_id), old_value])
			#self.modify_element_in_store(element_id, entry)
		elif action == 'DELETE':
			# Delete the entry from the board
			old_value = request.forms.get('old_value')
			self.board_editdelete_history.append([int(timestamp), action, entry, element_id, int(process_id), old_value])
			#self.delete_element_from_store(element_id)

	# ------------------------------------------------------------------------------------------------------
	# COMMUNICATION FUNCTIONS
	# ------------------------------------------------------------------------------------------------------
	def contact_single_node(self, node_ip, path, payload=None, req='POST'):
		# Try to contact another server (node) through a POST or GET, once
		success = False
		try:
			if 'POST' in req:
				res = requests.post('http://{}{}'.format(node_ip, path), data=payload)
			elif 'GET' in req:
				res = requests.get('http://{}{}'.format(node_ip, path))
			else:
				raise Exception('Non implemented feature!')
				# print 'Non implemented feature!'
			# result is in res.text or res.json()
			print(res.text)
			if res.status_code == 200:
				success = True
		except Exception as e:
			print e
		return success


	def propagate_to_nodes(self, path, payload=None, req='POST'):
		# global vessel_list, node_id

		for node_id, node_ip in self.node_list.items():
			if int(node_id) != int(self.node_id):  # don't propagate to yourself
				success = self.contact_single_node(node_ip, path, payload, req)
				if not success:
					print "\n\nCould not contact node {}\n\n".format(self.node_id)

	# ------------------------------------------------------------------------------------------------------
	# BOARD FUNCTIONS
	# ------------------------------------------------------------------------------------------------------

	def add_new_element_to_store(self, entry_sequence, element, propagated_call = False):
		success = False
		try:
			if not propagated_call:
				self.entry_id += 1
				entry_sequence = self.entry_id
			if entry_sequence not in self.board:
				self.board[entry_sequence] = element
				success = True
		except Exception as e:
			print e
		return success
	
	def modify_element_in_store(self, entry_sequence, modified_element):
		success = False
		try:
			if entry_sequence in self.board:
				self.board[entry_sequence] = modified_element
			success = True
		except Exception as e:
			print e
		return success

	def delete_element_from_store(self, entry_sequence):
		success = False
		try:
			# If it does not exist we count it as a successful delete as well
			if entry_sequence in self.board:
				del self.board[entry_sequence]
			success = True
		except Exception as e:
			print e
		return success


	# ------------------------------------------------------------------------------------------------------
	# HELPER FUNCTIONS
	# ------------------------------------------------------------------------------------------------------

	def increase_logical_timer(self, timestamp=0):
		default_add = 2
		self.logical_clock = max(self.logical_clock, int(timestamp)) + default_add
		print("Logical clock: ",self.logical_clock)

	def sort_board(self):
		time.sleep(10)
		self.board_add_history = sorted(self.board_add_history, key=itemgetter(4), reverse=True)
		self.board_add_history = sorted(self.board_add_history, key=itemgetter(0))
		add_list = copy.deepcopy(self.board_add_history)
		element_id = 0
		increment = 0
		for i in range(0, len(add_list)):
			if(element_id == add_list[i][3]):
				increment += 1
			element_id = add_list[i][3]
			entry = add_list[i][2]
			self.board[element_id + increment] = entry
		self.board_all_history += add_list
		del self.board_add_history[:len(add_list)]
		print("-- .. ",self.board_add_history)
		self.apply_modifications_and_deletions()

	def apply_modifications_and_deletions(self):
		self.board_editdelete_history = sorted(self.board_editdelete_history, key=itemgetter(4), reverse=True)
		self.board_editdelete_history = sorted(self.board_editdelete_history, key=itemgetter(0))
		temp_list = []
		for i in range(0, len(self.board_editdelete_history)-1):
			for z in range(i+1, len(self.board_editdelete_history)):
				if(self.board_editdelete_history[i][3] == self.board_editdelete_history[z][3]):
					if(self.board_editdelete_history[i][1] == "DELETE" and not self.board_editdelete_history[z][1] == "DELETE"):
						temp_list.append(z)
					else:
						temp_list.append(i)
		for i in reversed(temp_list):
			self.board_editdelete_history.pop(i)
		print(".. -- ",self.board_editdelete_history)
		for item in self.board_editdelete_history:
			for key, value in self.board.items():
				if(value == item[5] and item[1] == "MODIFY"):
					self.modify_element_in_store(key, item[2])
					break
				elif(value == item[5] and item[1] == "DELETE"):
					self.delete_element_from_store(key)
					break
				elif(item[1] == "MODIFY"):
					self.modify_element_in_store(item[3], item[2])
					break
				elif(item[1] == "DELETE"):
					self.delete_element_from_store(item[3])
					break
		self.board_all_history += self.board_editdelete_history
		del self.board_editdelete_history[:]
		self.thread_active = False

# ------------------------------------------------------------------------------------------------------
# EXECUTION
# ------------------------------------------------------------------------------------------------------
def main():

	parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
	parser.add_argument('--id', nargs='?', dest='nid', default=1, type=int, help='This server ID')
	parser.add_argument('--vessels', nargs='?', dest='nbv', default=1, type=int,
						help='The total number of nodes present in the system')
	args = parser.parse_args()
	node_id = args.nid
	node_list = {}
	# We need to write the other nodes IP, based on the knowledge of their number
	for i in range(1, args.nbv + 1):
		node_list[str(i)] = '10.1.0.{}'.format(str(i))
	try:
		server = Server(host=node_list[str(node_id)], port=80, node_list = node_list, node_id = node_id)
		server.start()
	except Exception as e:
		print e
		traceback.print_exc() 
# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
	main()