let audio = new Audio();  // Create an audio element without a source initially

async function fetchAndPlayAudio() {
    try {
        let timestamp = new Date().getTime();

        // Fetch and play the actual audio file
        audio.src = `/get_audio_file?ts=${timestamp}`;
        await audio.play();

        // Fetch and display the text file
        const response = await fetch(`/get_text_file?ts=${timestamp}`);
        const newText = await response.text();
        document.getElementById('dynamicText').innerHTML = '';
        typeWriter(newText, 0);

        // Fetch the audio duration
        const duration = await fetch(`/serve_audio?ts=${timestamp}`);
        const data = await duration.json();  // Parse the JSON response

        // Schedule the next audio fetch based on the duration
        setTimeout(fetchAndPlayAudio, data.next_run_in_sec * 1000);
    } catch (error) {
        console.error('Error rendering podcast:', error);
    }
}


// Typewriter effect function
function typeWriter(text, i, callback) {
    if (i < text.length) {
        let currentChar = text.charAt(i);
        if (currentChar === '\n') {
            document.getElementById("dynamicText").innerHTML += '<br>';
        } else {
            document.getElementById("dynamicText").innerHTML += currentChar;
        }
        i++;
        setTimeout(function() {
            typeWriter(text, i, callback);
        }, 50);
    } else if (callback) {
        callback();
    }
}


// Function to initialize audio and text on page load
window.onload = function() {
    // Initiate user interaction for audio playback only if there's an active podcast
    const startButton = document.createElement('button');
    startButton.innerText = 'Start';
    startButton.id = 'startPodcastBtn';
    startButton.style.position = 'absolute';
    startButton.style.top = '20px';
    startButton.style.right = '25px';
    startButton.style.padding = '10px 20px';
    startButton.style.fontSize = '1em';
    startButton.style.fontWeight = 'bold';
    document.body.appendChild(startButton);

    startButton.onclick = function() {
        fetchAndPlayAudio();
        // updateText();
        // Remove the start button after initiating
        startButton.remove();
        startButton.disabled = true;
        // setInterval(fetchAndPlayAudio, 26000);
        // setInterval(updateText, 26000);
    }
}


// Email validation function
function validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}


// Enable chat when entity and valid email are provided
function enableChat() {
    const entity = document.getElementById('entity').value;
    const email = document.getElementById('email').value;

    if (entity && validateEmail(email)) {
        // Enable comment input and send button
        document.getElementById('commentInput').disabled = false;
        document.getElementById('sendCommentBtn').disabled = false;

        // Disable the input fields and enable button after submission
        document.getElementById('entity').disabled = true;
        document.getElementById('email').disabled = true;
        document.getElementById('enableChatBtn').disabled = true;
    } else {
        alert('Please select an entity and provide a valid email.');
    }
}


// Function to fetch comments from the server
async function fetchComments() {
    try {
        const response = await fetch(`/get_recent_comments`);
        const data = await response.json();

        if (data.comments && data.comments.length > 0) {
            data.comments.forEach(commentData => {
                displayComment(commentData.comment, commentData.comment_timestamp);
            });
        }
    } catch (error) {
        console.error('Error fetching comments:', error);
    }
}


// Function to display a comment in the UI
function displayComment(comment, timestamp) {
    if (comment.trim()) {
        const commentBox = document.createElement('div');
        commentBox.classList.add('commentBox');
        commentBox.textContent = `(${new Date(timestamp).toLocaleTimeString()}) ${comment}`;
        document.getElementById('recentComments').prepend(commentBox);
    }
}


// Start fetching comments every 40 seconds
setInterval(fetchComments, 40000);  // Poll the server every 40 seconds


// Function to post comment
async function postComment() {
    const comment = document.getElementById('commentInput').value;
    const entity = document.getElementById('entity').value;
    const email = document.getElementById('email').value;

    if (comment.trim()) {

        // Clear the comment input field
        document.getElementById('commentInput').value = '';

        // Send the comment to the server to save in the database
        try {
            const response = await fetch('/post_comment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    entity: entity,
                    email: email,
                    comment: comment
                })
            });

            const result = await response.json();
            const feedbackMessage = document.getElementById('feedbackMessage');

            if (response.ok && result.status === 'success') {
                feedbackMessage.innerText = 'Comment posted successfully!';
                feedbackMessage.style.color = 'white';
            } else {
                feedbackMessage.innerText = result.message || 'Failed to post comment. Please try again.';
                feedbackMessage.style.color = 'red';
            }

            // Remove the feedback message after 5 seconds
            setTimeout(() => {
                feedbackMessage.innerText = '';
            }, 5000);

        } catch (error) {
            console.error('Error posting comment:', error);
            const feedbackMessage = document.getElementById('feedbackMessage');
            feedbackMessage.innerText = 'An error occurred. Please try again.';
            feedbackMessage.style.color = 'red';
            setTimeout(() => {
                feedbackMessage.innerText = '';
            }, 5000);
        }
    }
}
