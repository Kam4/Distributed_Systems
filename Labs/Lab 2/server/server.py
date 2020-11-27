# coding=utf-8
# ------------------------------------------------------------------------------------------------------
# TDA596 - Lab 1
# server/server.py
# Input: Node_ID total_number_of_ID
# Student: John Doe
# ------------------------------------------------------------------------------------------------------
import traceback
import sys
import time
import json
import argparse
from threading import Thread
from collections import deque

from bottle import Bottle, run, request, template
import requests
# ------------------------------------------------------------------------------------------------------
try:
	app = Bottle()

	# board stores all message on the system
	board = {0: "Welcome to Distributed Systems Course"}

	#Globa_id for elements so that each element gets a unique ID
	global_id = 0

	has_leader = False
	ongoing_election = False
	leader_id = 0
	locked = False

	leader_queue = deque()
	queue = deque()


	# ------------------------------------------------------------------------------------------------------
	# BOARD FUNCTIONS
	# You will probably need to modify them
	# ------------------------------------------------------------------------------------------------------

	# This functions will add an new element

	
	def add_new_element_to_store(entry_sequence, element, is_propagated_call=False):
		global board, node_id, global_id
		success = False
		if(not is_propagated_call):
			increase_global_id()
			entry_sequence = global_id
		try:
			if entry_sequence not in board:
				board[entry_sequence] = element
				success = True
		except Exception as e:
			print e
		#For each new entry increment global ID
		return success

	#Modify Entry in the board
	def modify_element_in_store(entry_sequence, modified_element, is_propagated_call=False):
		global board, node_id
		success = False
		try:
			board[entry_sequence] = modified_element
			success = True
		except Exception as e:
			print e
		return success
	
	#Delete Entry in the board
	def delete_element_from_store(entry_sequence, is_propagated_call=False):
		global board, node_id
		success = False
		try:
			del board[entry_sequence]
			success = True
		except Exception as e:
			print e
		return success

	# ------------------------------------------------------------------------------------------------------
	# ROUTES
	# ------------------------------------------------------------------------------------------------------
	# a single example (index) for get, and one for post
	# ------------------------------------------------------------------------------------------------------
	# No need to modify this
	@app.route('/')
	def index():
		global board, node_id, has_leader, ongoing_election

		if(not has_leader and not ongoing_election):
			print("No leader.. Starting election for {}!".format(node_id))
			thread_start = Thread(target=send_election_to_vessels,
					args=('/election/start_election_and_request', {"process_id": node_id}, "POST"))
			thread_start.daemon = True
			thread_start.start()
			thread_time = Thread(target=time_to_results,
					args=())
			thread_time.daemon = True
			thread_time.start()
			ongoing_election = True

			print("Election started!")

		return template('server/index.tpl', board_title='Vessel {}'.format(node_id),
						board_dict=sorted({"0": board, }.iteritems()), members_name_string='Andreas Månsson, Kamil Mudy and Tulathorn Sripongpankul')

	@app.get('/board')
	def get_board():
		global board, node_id
		print board
		return template('server/boardcontents_template.tpl', board_title='Vessel {}'.format(node_id), board_dict=sorted(board.iteritems()))

	# ------------------------------------------------------------------------------------------------------

	@app.post('/board')
	def client_add_received():
		'''Adds a new element to the board
		Called directly when a user is doing a POST request on /board'''
		global board, node_id, vessel_list, leader_id, leader_queue
		try:
			new_entry = request.forms.get('entry')
			element_id = global_id
			if(node_id == leader_id):
				leader_queue.append(new_entry)
				add_to_queue(process_id=node_id)
				return True
			add_to_queue(payload={"/leader/store_data": new_entry})
			contact_leader('/leader/request_access', {"process_id": node_id})
			return True
		except Exception as e:
			print e
		return False

	@app.post('/access_granted')
	def access_granted():
		global vessel_list, leader_id
		for i in range(0, len(queue)):
			queue_item = queue.popleft()
			path, entry = queue_item.items()[0]
			contact_vessel(vessel_list[str(leader_id)], path, {"entry":entry}, 'POST')
		contact_vessel(vessel_list[str(leader_id)], "/leader/request_done")


	@app.post('/board/<element_id:int>/')
	def client_action_received(element_id):
		global board, node_id, vessel_list, leader_id, leader_queue

		entry = request.forms.get('entry')

		delete_option = request.forms.get('delete')

		# 0 = modify, 1 = delete
		if(int(delete_option) == 0):
			add_to_queue(payload={"/leader/modify_data/"+str(element_id): entry})
		elif(int(delete_option) == 1):
			add_to_queue(payload={"/leader/delete_data/"+str(element_id): entry})
		contact_leader('/leader/request_access', {"process_id": node_id})
		return

	# With this function you handle requests from other nodes like add modify or delete
	@app.post('/propagate/<action>/<element_id:int>')
	def propagation_received(action, element_id):
		# get entry from http body
		entry = request.forms.get('entry')
		print "the action is", action

		
		#Check request type
		if(action == "ADD"):
			add_new_element_to_store(element_id, entry, True)
			return

		if(action == "DELETEorMODIFY"):
			delete_option = request.forms.get("delete")
			if(int(delete_option) == 0):
				modify_element_in_store(element_id, entry, True)
				return
			if(int(delete_option) == 1):
				delete_element_from_store(element_id)
				return

	# New propagate function to handle all request from other node here.

	@app.post('/election/<action>')
	def election(action):
		global vessel_list, has_leader, ongoing_election, node_id, leader_id

		process_id = request.forms.get("process_id")

		print("Got a request from node: {} and I am node: {}".format(process_id, node_id))

		if(action == "start_election_and_request"):
			if(int(process_id) < int(node_id)):
				print("Got election request from {}, I am bigger, sending response!".format(process_id))
				contact_vessel(vessel_list[process_id],  "/election/response_election", {"process_id": node_id})
			ongoing_election = True
			print("Got a start election notice, sending my election requests out!")
			thread = Thread(target=send_election_to_vessels,
				args=("/election/request_election", {"process_id": node_id}, "POST"))
			thread.daemon = True	
			thread.start()

			#Thread to keep track of time
			thread_time = Thread(target=time_to_results,
				args=())
			thread_time.daemon = True
			thread_time.start()
			return

		if(action == "request_election"):
			if(int(process_id) < int(node_id)):
				print("Got election request, I am bigger, sending response! ")
				contact_vessel(vessel_list[process_id], "/election/response_election", {"process_id": node_id})
				return
			return

		if(action == "response_election"):
			print("Received response in election, I am not leader.")
			ongoing_election = False
			return

		if(action == "election_result"):
			print("Got a new leader!")
			ongoing_election = False
			has_leader = True
			leader_id = int(process_id)
			return
		return

	# ------------------------------------------------------------------------------------------------------
	# Leader Communication
	# ------------------------------------------------------------------------------------------------------

	@app.post('/leader/request_access')
	def request_access():
		print("Got a request access call")
		process_id = request.forms.get("process_id")
		add_to_queue(process_id = int(process_id))

	@app.post('/leader/request_done')
	def request_done():
		global locked, queue
		print("Current node is done and has sent a request done, unlocking for next in queue.")
		queue.popleft()
		locked = False
		return

	@app.post('/leader/store_data')
	def store_data():
		global locked, global_id

		#increase_global_id()

		print("Current node with access has sent data to store.")

		entry = request.forms.get("entry")
		add_new_element_to_store(global_id, entry, False)

		thread = Thread(target=propagate_to_vessels,
			args=('/propagate/ADD/' + str(global_id), {"entry": entry}, 'POST'))
		thread.daemon = True
		thread.start()

	@app.post('/leader/modify_data/<element_id:int>')
	def modify_data(element_id):

		print("Current node with access has sent data to modify")

		entry = request.forms.get("entry")

		delete_option = 0 #only modifying here

		modify_element_in_store(element_id, entry, False)

		thread = Thread(target=propagate_to_vessels,
			args=('/propagate/DELETEorMODIFY/' + str(element_id), {'entry': entry, "delete": delete_option}, 'POST'))
		thread.daemon = True
		thread.start()

	@app.post('/leader/delete_data/<element_id:int>')
	def delete_data(element_id):

		print("Current node with access has sent data to delete")

		delete_option = 1 #only modifying here

		delete_element_from_store(element_id, False)

		thread = Thread(target=propagate_to_vessels,
			args=('/propagate/DELETEorMODIFY/' + str(element_id), {"delete": delete_option}, 'POST'))
		thread.daemon = True
		thread.start()




	
	# ------------------------------------------------------------------------------------------------------
	# DISTRIBUTED COMMUNICATIONS FUNCTIONS
	# ------------------------------------------------------------------------------------------------------

	def contact_vessel(vessel_ip, path, payload=None, req='POST'):
		# Try to contact another server (vessel) through a POST or GET, once
		success = False
		try:
			if 'POST' in req:
				res = requests.post(
					'http://{}{}'.format(vessel_ip, path), data=payload)
			elif 'GET' in req:
				res = requests.get('http://{}{}'.format(vessel_ip, path))
			else:
				print 'Non implemented feature!'
			# result is in res.text or res.json()
			print(res.text)
			if res.status_code == 200:
				success = True
		except Exception as e:
			print e
		return success

	def propagate_to_vessels(path, payload=None, req='POST'):
		global vessel_list, node_id

		for vessel_id, vessel_ip in vessel_list.items():
			if int(vessel_id) != node_id:  # don't propagate to yourself
				success = contact_vessel(vessel_ip, path, payload, req)
				if not success:
					print "\n\nCould not contact vessel {}\n\n".format(vessel_id)


	def send_election_to_vessels(path, payload=None, req="POST"):
		global vessel_list, node_id

		print("send_election_to_vessels()")

		for vessel_id, vessel_ip in vessel_list.items():
			if int(vessel_id) > node_id:
				success = contact_vessel(vessel_ip, path, payload, req)
				if not success:
					print "\n\nCould not contact vessel {}\n\n".format(vessel_id)

	def contact_leader(path, payload=None, req="POST"):
		global vessel_list, leader_id
		print("contacting leader...")
		success = False
		try:
			if 'POST' in req:
				res = requests.post(
					'http://{}{}'.format(vessel_list[str(leader_id)], path), data=payload)
			elif 'GET' in req:
				res = requests.get('http://{}{}'.format(vessel_list[str(leader_id)], path))
			else:
				print 'Non implemented feature!'
			# result is in res.text or res.json()
			print(res.text)
			if res.status_code == 200:
				success = True
			else:
				print("The call did not have status code 200")
		except Exception as e:
			print e
		return success

	# ------------------------------------------------------------------------------------------------------
	# HELPER FUNCTIONS
	# ------------------------------------------------------------------------------------------------------
			
	def increase_global_id():
		global global_id
		global_id += 1

	def time_to_results():
		global node_id, ongoing_election, has_leader, ongoing_election, leader_id

		time_voted = time.time()
		buffer_time = 2
		time_now = time.time()

		while(time_now - time_voted < buffer_time):
			print("Waiting for time to be end")
			time_now = time.time()
			time.sleep(0.2)

		if(ongoing_election):
			print("I won the election, propagating this information!")
			propagate_to_vessels("/election/election_result", {"process_id":node_id}, "POST")
			has_leader = True
			ongoing_election = False
			leader_id = node_id

			thread_resource = Thread(target=handle_resource_lock,
				args=())
			thread_resource.daemon = True
			thread_resource.start()
		return	

	def add_to_queue(process_id = None, payload = None):
		global queue, leader_id, node_id
		if(leader_id == node_id and process_id):
			queue.append(process_id)
		elif(leader_id != node_id and payload):
			queue.append(payload)
		print("Added entry to queue")
		print(queue)

	def handle_resource_lock():
		global locked, vessel_list, queue, leader_id, leader_queue, global_id, node_id
		while(leader_id == node_id):
			if(not locked and len(queue) > 0):
				locked = True
				process_id = queue[0]
				if(process_id == leader_id):
					queue.pop()
					print("Resource queue right now: ", leader_queue)
					entry = leader_queue.pop()
					add_new_element_to_store(global_id, entry)
					thread_propagate = Thread(target=propagate_to_vessels,
						args=('/propagate/ADD/' + str(global_id), {"entry": entry}, 'POST'))
					thread_propagate.daemon = True
					thread_propagate.start()
					locked = False
				else:
					contact_vessel(vessel_list[str(process_id)], "/access_granted", {}, "POST")
			time.sleep(0.05)
	
	# ------------------------------------------------------------------------------------------------------
	# EXECUTION
	# ------------------------------------------------------------------------------------------------------

	def main():
		global vessel_list, node_id, app

		port = 80
		parser = argparse.ArgumentParser(
			description='Your own implementation of the distributed blackboard')
		parser.add_argument('--id', nargs='?', dest='nid',
							default=1, type=int, help='This server ID')
		parser.add_argument('--vessels', nargs='?', dest='nbv', default=1,
							type=int, help='The total number of vessels present in the system')
		args = parser.parse_args()
		node_id = args.nid
		vessel_list = dict()
		# We need to write the other vessels IP, based on the knowledge of their number
		for i in range(1, args.nbv+1):
			vessel_list[str(i)] = '10.1.0.{}'.format(str(i))

		try:
			run(app, host=vessel_list[str(node_id)], port=port)
		except Exception as e:
			print e
	# ------------------------------------------------------------------------------------------------------
	if __name__ == '__main__':
		main()


except Exception as e:
	traceback.print_exc()
	while True:
		time.sleep(60.)
