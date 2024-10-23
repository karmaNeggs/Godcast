from flask import Flask, redirect, render_template, send_file, abort, request, jsonify, json, url_for
import os
import logging
from speech import run_podcast  # Import the function from speech.py

import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from connection_imports import db_connector, get_podcast_details_fe, get_entity_list_from_db
from flask import session
from flask_cors import CORS
from datetime import datetime, timedelta, timezone # Added import for datetime
import time
from mutagen.mp3 import MP3


# Initialize Flask
app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing if needed

# Set up secret key for session management
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_secret_key_here')  # Replace with a secure key in production

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables to manage podcast state
current_pc_id = None
last_comment_fetch_ts = None
entity_list_global = []
pc_topic_global = ""
participants_global = []
next_run_time_utc = None


# single run to fetch details when server runs
podcast_details = get_podcast_details_fe()
if podcast_details:
    current_pc_id, pc_topic_global, participants_global = podcast_details
    logger.info("podcast details fetched")
else:
    current_pc_id = None  # No active podcast
    pc_topic_global = "No Active Podcast"
    participants_global = []

#Fetch entity list from the database
entity_list_global = get_entity_list_from_db()


def get_audio_duration(file_path):
    audio = MP3(file_path)
    return audio.info.length


###########################################################################################
################## Main rendering  functions
###########################################################################################


# define scheduled job that RUNS PODCAST
def scheduled_job():

    global next_run_time_utc
    global duration
    try:
        is_audio_ready = run_podcast(current_pc_id,)
        
    except Exception as e:
        logger.error(f"Error in scheduled_job: {e}")

    if is_audio_ready:
        audio_file = 'static/audio.mp3'
        duration = get_audio_duration(audio_file)

        internal_run_time_utc = datetime.fromtimestamp(time.time() + duration, tz=timezone.utc)

        next_run_time_utc = datetime.fromtimestamp(time.time() + duration + 5, tz=timezone.utc)
        print(f"corrected timestamp: {next_run_time_utc}")
        scheduler.add_job(scheduled_job, trigger='date', run_date= internal_run_time_utc)

    else:
        logger.info(f"WARNING Audio not ready")
        scheduler.add_job(func=scheduled_job, trigger="interval", seconds=60)
        next_run_time_utc = datetime.fromtimestamp(time.time() +  5, tz=timezone.utc)

# scheduler.add_job(func=scheduled_job, trigger="interval", seconds=26)

scheduler = BackgroundScheduler()
scheduler.start()

# Start the first podcast
scheduled_job()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())


###########################################################################################
################## Main rendering  functions
###########################################################################################

@app.route('/')
def index():
    global current_pc_id, pc_topic_global, participants_global
    try:

        # # Fetch current podcast details
        # podcast_details = get_podcast_details_fe()
        # if podcast_details:
        #     current_pc_id, pc_topic_global, participants_global = podcast_details
        #     logger.info("podcast details fetched")
        # else:
        #     current_pc_id = None  # No active podcast
        #     pc_topic_global = "No Active Podcast"
        #     participants_global = []

        return render_template('index.html', 
                               entity_list=participants_global, 
                               pc_topic=pc_topic_global,
                               participants=participants_global)
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        # Provide fallback data
        fallback_entities = ['Truckers', 'Traders', 'Software engineers']
        fallback_topic = "who should go to heaven"
        fallback_participants = []
        return render_template('index.html', 
                               entity_list=fallback_entities, 
                               pc_topic=fallback_topic,
                               participants=fallback_participants)


#serve the audio and text stream

@app.route('/serve_audio')
def serve_audio():
    try:
        audio_path = "static/audio.mp3"

        if not os.path.exists(audio_path):
            abort(404, description="Audio file not found")

        # audio = MP3(audio_path)
        # duration = int(audio.info.length)  # Get the audio duration

        return jsonify({
            "next_run_time_utc": next_run_time_utc.isoformat(),
            "duration": duration*1000  # Return the audio duration
        })

    except Exception as e:
        abort(500, description="Internal Server Error")


@app.route('/get_audio_file')
def get_audio_file():
    audio_path = "static/audio.mp3"
    if os.path.exists(audio_path):
        return send_file(audio_path, mimetype='audio/mp3')
    else:
        abort(404, description="Audio file not found")


@app.route('/get_text_file')
def get_text_file():
    text_path = 'typewrite.txt'
    if os.path.exists(text_path):
        return send_file(text_path, mimetype='text/plain')
    else:
        abort(404, description="Text file not found")


@app.route('/post_comment', methods=['POST'])
def post_comment():
    try:
        data = request.json
        entity_id = data.get('entity')
        user_mail = data.get('email')
        comment = data.get('comment')
        comment_timestamp = datetime.now()
        global current_pc_id

        if not all([entity_id, user_mail, comment]):
            return jsonify({"status": "fail", "message": "Missing data"}), 400

        if not current_pc_id:
            return jsonify({"status": "fail", "message": "No active podcast to comment on."}), 400

        # Insert into the database
        conn, cursor = db_connector()
        if conn and cursor:
            cursor.execute(
                "INSERT INTO project.session_comments (pc_id, user_mail, entity_id, comment, comment_timestamp) "
                "VALUES (%s, %s, %s, %s, %s)",
                (current_pc_id, user_mail, entity_id, comment, comment_timestamp)
            )
            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"Comment added by {user_mail} for {entity_id} under pc_id {current_pc_id}")
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "fail", "message": "Database connection error"}), 500
    except Exception as e:
        logger.error(f"Error in post_comment: {e}")
        return jsonify({"status": "fail", "message": "Internal Server Error"}), 500


@app.route('/get_recent_comments', methods=['GET'])
def get_recent_comments():
    try:
        global current_pc_id
        global last_comment_fetch_ts

        if last_comment_fetch_ts is None:
            last_comment_fetch_ts = datetime.now(timezone.utc).isoformat()

        logger.info(f"last comment fetch {last_comment_fetch_ts} for {current_pc_id}")

        conn, cursor = db_connector()

        # Query comments newer than the last fetch timestamp
        query = """
        SELECT entity_id, comment, comment_timestamp 
        FROM project.session_comments 
        WHERE pc_id = %s 
        ORDER BY comment_timestamp ASC
        """
        cursor.execute(query, (current_pc_id,))
        rows = cursor.fetchall()

        # Return the comments as a JSON response
        comments = []
        for row in rows:
            comments.append({
                'entity_id': row[0],
                'comment': row[1],
                'comment_timestamp': row[2].isoformat()
            })

        cursor.close()
        conn.close()

        # Update the global last_fetch_timestamp to the latest comment fetched
        if rows:
            last_comment_fetch_ts = rows[-1][2].isoformat()

            logger.info(f"last_comment_fetch_ts {last_comment_fetch_ts}")

        return jsonify(comments=comments)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



###########################################################################################
################## Assisting functions BE
###########################################################################################



# @app.route('/fetch_podcast_list', methods=['POST'])
def fetch_podcast_list():
    connection, cursor = db_connector()
    if connection:
        try:
            # Fetch entities for dropdown
            cursor.execute("SELECT CONCAT(entity_id, '_', entity_name) AS entity_option FROM project.entity_info order by 1 asc;")
            entities = cursor.fetchall()
            entity_options = [entity[0] for entity in entities]
            
            # Fetch upcoming podcasts
            cursor.execute("""
                SELECT pc_begin_ts, pc_id, pc_topic, num_participants, pc_participants
                FROM project.podcast_roster
                ORDER BY pc_begin_ts ASC;
            """)
            podcasts = cursor.fetchall()
            
            podcast_list = []
            for podcast in podcasts:
                pc_begin_ts, pc_id, pc_topic, num_participants, pc_participants = podcast
                try:

                    pc_participants = json.loads(json.dumps(pc_participants))

                except:
                    pc_participants = []

                podcast_list.append({
                    "pc_begin_ts": pc_begin_ts.strftime('%Y-%m-%d %H:%M:%S'),
                    "pc_id": pc_id,
                    "pc_topic": pc_topic,
                    "num_participants": num_participants,
                    "pc_participants": pc_participants
                })

        except Exception as e:
            print(f"Error fetching data: {e}")
            entity_options = []
            podcast_list = []
        finally:
            cursor.close()
            connection.close()
    else:
        entity_options = []
        podcast_list = []

    return entity_options, podcast_list



@app.route('/backendplatoon', methods=['GET'])
def be_index():

    entity_options, podcast_list = fetch_podcast_list()

    return render_template('backend.html', entities=entity_options, podcasts=podcast_list)


@app.route('/add_podcast', methods=['POST'])
def add_podcast():
    connection, cursor = db_connector()
    if not connection:
        return redirect(url_for('be_index'))
    
    try:
        pc_begin_ts = request.form['pc_begin_ts']
        pc_id = request.form['pc_id']
        pc_topic = request.form['pc_topic']
        num_participants = int(request.form['num_participants'])
        pc_topic_context = request.form['pc_topic_context']
        
        # Get participants
        participants = []
        for i in range(1, num_participants+1):
            participant = request.form.get(f'participant_{i}')
            if participant:
                entity_id, entity_name = participant.split('_')
                participants.append({
                    "entity_id": entity_id,
                    "entity_name": entity_name
                })
        
        pc_participants = json.dumps(participants)
        
        # Insert into podcast_roster
        cursor.execute("""
            INSERT INTO project.podcast_roster (pc_begin_ts, pc_id, pc_topic, num_participants, pc_topic_context, pc_participants)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (pc_begin_ts, pc_id, pc_topic, num_participants, pc_topic_context, pc_participants))
        
        connection.commit()
    except Exception as e:
        print(f"Error adding podcast: {e}")
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('be_index'))


@app.route('/delete_podcast', methods=['POST'])
def delete_podcast():
    connection, cursor = db_connector()
    if not connection:
        return redirect(url_for('be_index'))
    
    try:
        pc_id = request.form['delete_pc_id']
        cursor.execute("""
            DELETE FROM project.podcast_roster
            WHERE pc_id = %s;
        """, (pc_id,))
        connection.commit()
    except Exception as e:
        print(f"Error deleting podcast: {e}")
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('be_index'))


@app.route('/add_entity', methods=['POST'])
def add_entity():
    connection, cursor = db_connector()
    if not connection:
        return redirect(url_for('be_index'))
    
    try:
        entity_id = request.form['entity_id']
        entity_name = request.form['entity_name']
        entity_qualities = request.form['entity_qualities']
        photo_url = request.form['photo_url']
        entity_url = request.form['entity_url']
        
        cursor.execute("""
            INSERT INTO project.entity_info (entity_id, entity_name, entity_qualities, Photo_url, entity_url)
            VALUES (%s, %s, %s, %s, %s);
        """, (entity_id, entity_name, entity_qualities, photo_url, entity_url))
        
        connection.commit()
    except Exception as e:
        print(f"Error adding entity: {e}")
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('be_index'))


@app.route('/update_entity', methods=['POST'])
def update_entity():
    connection, cursor = db_connector()
    if not connection:
        return redirect(url_for('be_index'))
    
    try:
        entity_id = request.form['update_entity_id']
        entity_name = request.form['update_entity_name']
        entity_qualities = request.form['update_entity_qualities']
        photo_url = request.form['update_photo_url']
        entity_url = request.form['update_entity_url']
        
        cursor.execute("""
            UPDATE project.entity_info
            SET entity_name = %s,
                entity_qualities = %s,
                Photo_url = %s,
                entity_url = %s
            WHERE entity_id = %s;
        """, (entity_name, entity_qualities, photo_url, entity_url, entity_id))
        
        connection.commit()
    except Exception as e:
        print(f"Error updating entity: {e}")
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('be_index'))


@app.route('/delete_entity', methods=['POST'])
def delete_entity():
    connection, cursor = db_connector()
    if not connection:
        return redirect(url_for('be_index'))
    
    try:
        entity_id = request.form['delete_entity_id']
        cursor.execute("""
            DELETE FROM project.entity_info
            WHERE entity_id = %s;
        """, (entity_id,))
        connection.commit()
    except Exception as e:
        print(f"Error deleting entity: {e}")
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('be_index'))


###########################################################################################
################## Assisting functions landing
###########################################################################################

@app.route('/landing', methods=['GET'])
def landing_index():

    entity_options, podcast_list = fetch_podcast_list()

    return render_template('landing.html', entities=entity_options, podcasts=podcast_list)


# Flask route to serve the entity lists in JSON format (if needed for AJAX)
@app.route('/get_entity_list')
def get_entity_list():
    try:
        return jsonify(participants_global)
    except Exception as e:
        logger.error(f"Error fetching entity list: {e}")
        return jsonify({"error": "Unable to fetch entity list"}), 500


@app.route('/get_global_entity_list')
def get_global_entity_list():
    try:
        return jsonify(entity_list_global)
    except Exception as e:
        logger.error(f"Error fetching global entity list: {e}")
        return jsonify({"error": "Unable to fetch global entity list"}), 500


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
