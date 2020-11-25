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

from bottle import Bottle, run, request, template
import requests
# ------------------------------------------------------------------------------------------------------
try:
    app = Bottle()

    # board stores all message on the system
    board = {0: "Welcome to Distributed Systems Course"}

    #Globa_id for elements so that each element gets a unique ID
    global_id = 1

    has_leader = False
    ongoing_election = False
    leader_id = 0




    # ------------------------------------------------------------------------------------------------------
    # BOARD FUNCTIONS
    # You will probably need to modify them
    # ------------------------------------------------------------------------------------------------------

    # This functions will add an new element

    
    def add_new_element_to_store(entry_sequence, element, is_propagated_call=False):
        global board, node_id, global_id
        success = False
        try:
            if entry_sequence not in board:
                board[entry_sequence] = element
                success = True
        except Exception as e:
            print e
        #For each new entry increment global ID
        global_id += 1
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
    	global board, node_id, has_leader
    	
    	if(not has_leader):
        	print("No leader.. Starting election for {}!".format(node_id))
    		thread_start = Thread(target=send_election_to_vessels,
                    args=('/election/start_election_and_request', {"process_id": node_id}, "POST"))
    		thread_start.daemon = True
        	thread_start.start()

    		print("Election started!")

        return template('server/index.tpl', board_title='Vessel {}'.format(node_id),
                        board_dict=sorted({"0": board, }.iteritems()), members_name_string='Andreas Månsson, Kamil Mudy and Tulathorn Sripongpankul')

    @app.get('/board')
    def get_board():
        global board, node_id
        print board
        return template('server/boardcontents_template.tpl', board_title='Vessel {}'.format(node_id), board_dict=sorted(board.iteritems()))

    # ------------------------------------------------------------------------------------------------------

    # You NEED to change the follow functions
    @app.post('/board')
    def client_add_received():
        '''Adds a new element to the board
        Called directly when a user is doing a POST request on /board'''
        global board, node_id
        try:
            new_entry = request.forms.get('entry')

            
            element_id = global_id
            add_new_element_to_store(element_id, new_entry)

            # you should propagate something
            # Please use threads to avoid blocking
            # thread = Thread(target=???,args=???)
            # For example: thread = Thread(target=propagate_to_vessels, args=....)
            # you should create the thread as a deamon with thread.daemon = True
            # then call thread.start() to spawn the thread

            # Propagate action to all other nodes example :
            thread = Thread(target=propagate_to_vessels,
                            args=('/propagate/ADD/' + str(element_id), {'entry': new_entry}, 'POST'))
            thread.daemon = True
            thread.start()
            return True
        except Exception as e:
            print e
        return False

    @app.post('/board/<element_id:int>/')
    def client_action_received(element_id):
        global board, node_id

        print "You receive an element"
        print "id is ", node_id
        # Get the entry from the HTTP body
        entry = request.forms.get('entry')

        delete_option = request.forms.get('delete')

        print "the delete option is ", delete_option
       
        # 0 = modify, 1 = delete
        if(int(delete_option) == 0):
            modify_element_in_store(element_id, entry, False)
        elif(int(delete_option) == 1):
            delete_element_from_store(element_id, False)

        # propage to other nodes
        thread = Thread(target=propagate_to_vessels,
                        args=('/propagate/DELETEorMODIFY/' + str(element_id), {'entry': entry, "delete": delete_option}, 'POST'))
        thread.daemon = True
        thread.start()

    # With this function you handle requests from other nodes like add modify or delete
    @app.post('/propagate/<action>/<element_id:int>')
    def propagation_received(action, element_id):
        # get entry from http body
        entry = request.forms.get('entry')
        print "the action is", action

        
        #Check request type
        if(action == "ADD"):
            add_new_element_to_store(global_id, entry)
            return

        if(action == "DELETEorMODIFY"):
            delete_option = request.forms.get("delete")
            print(":", type(delete_option), ":")
            if(int(delete_option) == 0):
                modify_element_in_store(element_id, entry, True)
                return
            if(int(delete_option) == 1):
                delete_element_from_store(element_id)
                return


    @app.post('/election/<action>')
    def election(action):
    	global has_leader, ongoing_election, node_id, leader_id

    	process_id = request.forms.get("process_id")

    	if(action == "start_election_and_request"):
			ongoing_election = True
			print("Got a start election notice, sending my election requests out!")
			thread = Thread(target=send_election_to_vessels,
				args=("/election/request_election", {}, "POST"))
			thread.daemon = True	
			thread.start()

			#Thread to keep track of time
			thread_time = Thread(target=time_to_results,
				args=())
			thread_time.daemon = True
			thread_time.start()
			return


    	if(action == "request_election" and ongoing_election):
    		if(process_id < node_id):
    			print("Got election request, I am bigger, sending response!")
    			contact_vessel(vessel_list[process_id], "/election/response_election")
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
    		leader_id = process_id
    		return

    	return





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
    	

    # ------------------------------------------------------------------------------------------------------
    # HELPER FUNCTIONS
    # ------------------------------------------------------------------------------------------------------

    def time_to_results():
		global node_id, ongoing_election, has_leader, ongoing_election, leader_id

		time_voted = time.time()
		buffer_time = 1
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
