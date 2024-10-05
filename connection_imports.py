import psycopg2
import json
import os
from datetime import datetime
import logging
import openai
from flask import jsonify

# Initialize OpenAI API
openai.api_key = os.environ.get('OPENAI_API_KEY', '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')  # Replace with your actual API key
model_name = "gpt-4o-mini"  # Ensure this matches the actual model name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def db_connector():
    """
    Connects to the PostgreSQL database and returns the connection and cursor.
    Replace the placeholders with your actual database credentials or use environment variables.
    """
    try:
        connection = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=os.environ.get('DB_PORT', '5432'),
            database=os.environ.get('DB_NAME', 'project_db'),
            user=os.environ.get('DB_USER', 'anupamvashist'),
            password=os.environ.get('DB_PASSWORD', 'onepassword')  # Use environment variables for security
        )
        cursor = connection.cursor()
        return connection, cursor
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
        return None, None

# def get_entity_list_from_db():
#     """
#     Fetches the list of entities from the database.
#     """
#     try:
#         conn, cursor = db_connector()
#         if conn and cursor:
#             cursor.execute("SELECT entity_name FROM project.entity_info;")
#             entities = cursor.fetchall()
#             cursor.close()
#             conn.close()
#             entity_names = [entity[0] for entity in entities]

#             return entity_names
#         else:
#             return []
#     except Exception as e:
#         logger.error(f"Error fetching entity list: {e}")
#         return []

def get_podcast_details_fe():
    """
    Fetches the current podcast's pc_topic and participants from the database.
    """
    try:
        connection, cursor = db_connector()
        if not connection or not cursor:
            logger.error("Database connection failed.")
            return None

        # Fetch current active podcast details
        cursor.execute("""
            SELECT pc_id, pc_topic, pc_participants
            FROM project.podcast_roster
            WHERE pc_begin_ts >= NOW()
            AND pc_conclusion IS NULL
            ORDER BY pc_begin_ts ASC
            LIMIT 1;
        """)

        podcast = cursor.fetchone()
        if not podcast:
            logger.info("No active podcast found.")
            cursor.close()
            connection.close()
            return None

        pc_id, pc_topic, pc_participants = podcast

        # Parse participants JSON
        try:
            participants = pc_participants
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing participants JSON: {e}")
            participants = []

        # Extract entity names

        participant_names = [participant['entity_name'] for participant in participants]

        cursor.close()
        connection.close()

        return (pc_id, pc_topic, participant_names)

    except Exception as e:
        logger.error(f"Error fetching podcast details: {e}")
        return None


def collect_variables(pc_id):
    """
    Collects necessary variables for the current podcast from the database.
    """
    try:
        connection, cursor = db_connector()
        if not connection or not cursor:
            logger.error("Database connection failed.")
            return None

        # Fetch podcast details
        cursor.execute("""
            SELECT pc_id, num_participants, pc_topic, pc_topic_context, pc_participants
            FROM project.podcast_roster
            WHERE pc_id = %s;
        """, (pc_id,))
        podcast = cursor.fetchone()
        if not podcast:
            logger.info("126 No active podcast found.")
            return None

        pc_id, num_participants, pc_topic, pc_topic_context, pc_participants = podcast

        # Parse participants to global
        participants = pc_participants

        # Ensure transcript file exists
        global transcript_filename
        
        transcript_filename = f"{pc_id}transcript.txt"
        if not os.path.exists(transcript_filename):
            open(transcript_filename, 'w').close()

        # Fetch entity qualities and comment context for each participant
        participants_data = []
        for participant in participants:
            entity_id = participant['entity_id']

            # Fetch entity qualities
            cursor.execute("""
                SELECT entity_qualities
                FROM project.entity_info
                WHERE entity_id = %s;
            """, (entity_id,))
            result = cursor.fetchone()
            entity_qualities = result if result else ""

            participants_data.append({
                "entity_id": entity_id,
                "entity_name": participant['entity_name'],
                "entity_qualities": entity_qualities,
                "comment_context": "",
            })

        logger.info("Participants data collected successfully.")
        return (participants_data, pc_id, num_participants, pc_topic, pc_topic_context)
    except Exception as e:
        logger.error(f"Error in collect_variables: {e}")
        return None


# keep pc_topic_context

def getnextresponse(participant, pc_topic, pc_topic_context, pc_podcast_context, latest_response, is_podcast_running, pc_id):
    
    """
    Generates the next response using OpenAI's API.
    """
    try:
        entity_id = participant['entity_id']
        entity_name = participant['entity_name']
        entity_qualities = participant['entity_qualities']
        pc_comment_context = participant['comment_context']

        # Read prompt from cast_prep.txt
        with open('prompts/cast_prep.txt', 'r') as file:
            prompt_template = file.read()

        # Construct the prompt
        prompt = f"""
        {prompt_template}
        Podcast Topic: {pc_topic}
        Previous talk Context: {pc_podcast_context}
        Entity Qualities: {entity_qualities}
        Comment Context: {json.dumps(pc_comment_context)}
        Latest Argument to Respond: {latest_response}
        """

        # Call OpenAI API
        response = openai.ChatCompletion.create(
            model=model_name,
            temperature=0.7,
            presence_penalty= 0.5,
            frequency_penalty= 0,
            max_tokens= 50,
            top_p= 0.9,
            n=1,
            messages=[{"role": "system", "content": prompt}]
        )

        # Extract text from response
        text_chunk = response.choices[0].message['content'].strip()
        if text_chunk.startswith('"') and text_chunk.endswith('"'):
            text_chunk = text_chunk[1:-1]

        logger.info(f"Generated text: {text_chunk}")

        # Save text to transcript
        with open(f"{pc_id}transcript.txt", "a") as file:
            # Write the text row
            file.write(text_chunk)

        return (text_chunk, 1)

    except Exception as e:
        logger.error(f"Error in getnextresponse: {e}")
        return ("Error generating response", 0)


def update_context(pc_id, participants_data, pc_topic_context, pc_podcast_context, podcast_conversation):
    """
    Updates the podcast context based on recent comments and transcript.
    """

    # Read prompt from comment_summary.txt
    with open('prompts/comment_summary.txt', 'r') as file:
                summary_prompt = file.read()

    try:
        connection, cursor = db_connector()
        if not connection or not cursor:
            logger.error("Database connection failed.")
            return

        ####################################  Update comment context in participants data ####################################
        ## CAUTION : Entity ID in comment table is actually entity name
        # Step A: Summarize user comments for each participant
        cursor.execute("""
            SELECT entity_id, comment
            FROM project.session_comments
            WHERE pc_id = %s
            ORDER BY comment_timestamp DESC
            LIMIT 30;
        """, (pc_id,))
        comments = cursor.fetchall()

        # Organize comments by entity_id
        comments_by_entity = {}
        for entity_id, comment in comments:
            if entity_id not in comments_by_entity:
                comments_by_entity[entity_id] = []
            comments_by_entity[entity_id].append(comment)

        #Update in participants data

        for participant in participants_data:

            try:
                comment_ = comments_by_entity[participant['entity_name']]
            except:
                comment_ = []
            

            summary = f"""
            {summary_prompt}
            Your_community_name: {entity_id}
            Podcast Topic: {pc_topic_context}
            Podcast_historical_context: {pc_podcast_context}
            Comments from users:
            {json.dumps(comment_)}

            """

            # Call OpenAI API for summary
            response = openai.ChatCompletion.create(
                model=model_name,
                temperature=0.7,
                presence_penalty= -1,
                frequency_penalty= 0,
                max_tokens= 110,
                top_p= 0.85,
                n=1,
                messages=[{"role": "system", "content": summary}]
            )

            comment_summary_reply = response.choices[0].message['content'].strip()
            
            participant['comment_context'] = comment_summary_reply
        
        logger.info(f"Comment context updated")


####################################  Update podcast context in global vars ####################################

        # Step B: Summarize the podcast
        # Read prompt from cast_summary.txt
        with open('prompts/cast_summary.txt', 'r') as file:
            cast_summary_prompt = file.read()

        last_4 = podcast_conversation[-4:]

        # Prepare cast summary prompt
        cast_summary = f"""
        {cast_summary_prompt}
        Podcast topic:
        {pc_topic_context}
        Podcast_historical_context:
        {pc_podcast_context}
        Last 4 Responses:
        {'\n'.join(last_4)}
        """

        # Call OpenAI API for cast summary
        response = openai.ChatCompletion.create(
            model=model_name,
            messages=[{"role": "system", "content": cast_summary}]
        )
        cast_summary_reply = response.choices[0].message['content'].strip()

        pc_podcast_context = cast_summary_reply

        logger.info(f"Podcast context updated")

        #Return updated contexts
        logger.info(f"Contexts updated and returned")
        return participants_data, pc_podcast_context

        cursor.close()
        connection.close()

    except Exception as e:
        logger.error(f"Error in update_context: {e}")

    
def update_conclusion(pc_id, participants_data, pc_topic_context, pc_podcast_context, podcast_conversation):

    # Read prompt from cast_conclusion.txt
    with open('prompts/cast_conclusion.txt', 'r') as file:
        conclusion_prompt = file.read()

    try:
        # Read the entire transcript
        # conclusion = podcast_conversation
        logger.info(f"Podcast transcript: {podcast_conversation}")

        # Prepare the conclusion prompt
        conclusion = f"""
        {conclusion_prompt}
        Transcript of podcast:
        {podcast_conversation}
        Topic of podcast:
        {pc_topic_context}
        """

        response = openai.ChatCompletion.create(
            model=model_name,
            temperature=1.1,
            presence_penalty= 1,
            frequency_penalty= 0,
            max_tokens= 110,
            top_p= 0.9,
            n=1,
            messages=[{"role": "system", "content": conclusion}]
        )
        
        final_conclusion = response.choices[0].message['content']

        # Update the conclusion in podcast_roster
        connection, cursor = db_connector()
        if not connection or not cursor:
            logger.error("Database connection failed.")
            return None

        cursor.execute("""
            UPDATE project.podcast_roster
            SET pc_conclusion = %s
            WHERE pc_id = %s;
        """, (final_conclusion, pc_id))
        connection.commit()

        # Print podcast conclusion to console
        logger.info(f"Podcast Conclusion: {final_conclusion}")
        return (final_conclusion, 0)

    except Exception as e:
        logger.error(f"Error in conclusion: {e}")
