from gtts import gTTS
import logging
from connection_imports import collect_variables, getnextresponse, update_context, update_conclusion
import json
from random import randrange


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables to manage podcast state
is_podcast_running = 0
latest_argument_to_respond = "No Conversation history to show"
nx_response = ""
participant = []
accent = ['co.uk','co.in','com.ng','us', 'ca']

num_participants = 0 
pc_topic  = ""
pc_topic_context = ""
pc_participants = []
pc_comment_context = []
pc_podcast_context = ""
podcast_conversation = []
participants_data = []
max_rounds = 3

def run_podcast(pc_id):

    global is_podcast_running
    global latest_argument_to_respond
    global nx_response
    global pc_participants
    global pc_comment_context
    global pc_podcast_context
    global pc_topic
    global pc_topic_context
    global participants_data
    global podcast_conversation
    global participant
    global max_rounds

    try:
        if is_podcast_running > 0 and is_podcast_running <= max_rounds:
            logger.info("Podcast is currently running.")

        # Fetch prompt to give to GPT
            logger.info("Generating response from OpenAI.")
            nx_response, is_podcast_running_flag = getnextresponse(participant, pc_topic, pc_topic_context, pc_podcast_context, latest_argument_to_respond, is_podcast_running, pc_id)

            Speaker = participant['entity_name']

            #Update next participant
            participant_index = randrange(len(participants_data))
            participant = participants_data[participant_index]

            is_podcast_running += 1

            # Check if contexts need updating
            if is_podcast_running % 4 == 0:
                participants_data, pc_podcast_context = update_context(pc_id, participants_data, pc_topic_context, pc_podcast_context, podcast_conversation)
            else:
                pass

        #conclude podcast    
        elif is_podcast_running > max_rounds:
            # set is_podcast_running to 0 by function return val
            nx_response, is_podcast_running_flag = update_conclusion(pc_id, participants_data, pc_topic_context, pc_podcast_context, podcast_conversation)
            Speaker = 'Godcast'
            is_podcast_running = 0
            participant_index = 4

        else:
            # Fetch the current participants data from the database
            podcast_details = collect_variables(pc_id)
            if podcast_details:
                participants_data, pc_id, num_participants, pc_topic, pc_topic_context = podcast_details

                logger.info("variables collected")

                #re-initiate contexts before each podcast
                podcast_conversation = []
                pc_podcast_context = ""

                is_podcast_running = 1
                is_podcast_running_flag = 1

                participant_index = randrange(len(participants_data))
                participant = participants_data[participant_index]

                logger.info("Generating response from OpenAI.")
                nx_response, is_podcast_running_flag = getnextresponse(participant, pc_topic, pc_topic_context, pc_podcast_context, latest_argument_to_respond, is_podcast_running, pc_id)

                Speaker = participant['entity_name']

            else:
                logger.info("No active podcast to generate inputs.")
                return

            
        if not participants_data:
            logger.error("No participants data available.")
            return

        else:

            # Format the response with entity name
            formatted_response = f"{Speaker}: {nx_response}"

            # Generate audio using gTTS save audio using gTTS as 'audio.mp3'
            tts = gTTS(nx_response, lang = 'en', tld = accent[participant_index] , slow=False)
            tts.save('audio.mp3')
            logger.info("Audio file updated with new speech.")

            # Generate text and save to 'typewrite.txt'
            with open("typewrite.txt", 'w') as file2write:
                file2write.write(formatted_response)
            logger.info("Typewrite text file updated with new speech.")

            # Reset latest argument
            latest_argument_to_respond = formatted_response

            # update podcast conversation list
            podcast_conversation.append(latest_argument_to_respond)
            return

            if Speaker == 'Godcast':
                time.sleep(50)

    except Exception as e:
        logger.error(f"Error in run_podcast: {e}")
