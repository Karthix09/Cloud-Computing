// ==================== CONFIGURATION ====================
const API_URL = '/api/chat';
const SEARCH_URL = '/api/bus-stops/search';
const NEARBY_URL = '/api/bus-stops/nearby';

let sessionId = generateSessionId();

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('userInput');
    
    // Send message on Enter key
    input.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    // Focus on input
    input.focus();
});

// ==================== MAIN FUNCTIONS ====================

/**
 * Send user message to chatbot
 */
async function sendMessage(predefinedMessage = null) {
    const input = document.getElementById('userInput');
    const userMessage = predefinedMessage || input.value.trim();
    
    if (!userMessage) return;
    
    // Clear input
    if (!predefinedMessage) {
        input.value = '';
    }
    
    // Display user message
    addMessage(userMessage, 'user');
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        // Send to backend
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: userMessage,
                session_id: sessionId
            })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        removeTypingIndicator();
        
        // Handle response
        handleBotResponse(data);
        
    } catch (error) {
        console.error('Error:', error);
        removeTypingIndicator();
        addMessage('❌ Sorry, something went wrong. Please try again.', 'bot');
    }
    
    // Refocus input
    input.focus();
}

/**
 * Send quick message (from button)
 */
function sendQuickMessage(message) {
    sendMessage(message);
}

/**
 * Handle bot response
 */
function handleBotResponse(data) {
    console.log('Bot response:', data);
    
    const responseType = data.type;
    
    if (responseType === 'request_location') {
        // Request user location
        addMessage(data.response, 'bot');
        requestUserLocation();
    } else if (responseType === 'multiple_matches') {
        // Show bus stop selection
        addMessage(data.response, 'bot');
        if (data.stops && data.stops.length > 0) {
            addBusStopOptions(data.stops);
        }
    } else if (responseType === 'nearby_stops') {
        // Show nearby stops
        addMessage(data.response, 'bot');
        if (data.stops && data.stops.length > 0) {
            addBusStopOptions(data.stops);
        }
    } else {
        // Regular text response
        addMessage(data.response, 'bot');
    }
}

/**
 * Add message to chat
 */
function addMessage(text, sender) {
    const messagesDiv = document.getElementById('chatMessages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = sender === 'user' ? '👤' : '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    // Convert markdown-style bold to HTML
    const formattedText = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Split by newlines and create paragraphs
    const paragraphs = formattedText.split('\n').filter(p => p.trim());
    paragraphs.forEach(para => {
        const p = document.createElement('p');
        p.innerHTML = para;
        content.appendChild(p);
    });
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    
    messagesDiv.appendChild(messageDiv);
    
    // Scroll to bottom
    scrollToBottom();
}

/**
 * Add bus stop selection options
 */
function addBusStopOptions(stops) {
    const messagesDiv = document.getElementById('chatMessages');
    
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'message bot-message';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    const optionsDiv = document.createElement('div');
    optionsDiv.className = 'bus-stop-options';
    
    stops.forEach(stop => {
        const button = document.createElement('button');
        button.className = 'bus-stop-btn';
        button.innerHTML = `
            <strong>${stop.description}</strong>
            <small>📍 ${stop.road} • Code: ${stop.code}</small>
        `;
        button.onclick = () => selectBusStop(stop.code);
        optionsDiv.appendChild(button);
    });
    
    content.appendChild(optionsDiv);
    optionsContainer.appendChild(avatar);
    optionsContainer.appendChild(content);
    
    messagesDiv.appendChild(optionsContainer);
    scrollToBottom();
}

/**
 * User selected a bus stop
 */
function selectBusStop(busStopCode) {
    sendMessage(`Bus arrivals at ${busStopCode}`);
}

/**
 * Show typing indicator
 */
function showTypingIndicator() {
    const messagesDiv = document.getElementById('chatMessages');
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot-message';
    typingDiv.id = 'typingIndicator';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    
    content.appendChild(indicator);
    typingDiv.appendChild(avatar);
    typingDiv.appendChild(content);
    
    messagesDiv.appendChild(typingDiv);
    scrollToBottom();
}

/**
 * Remove typing indicator
 */
function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

/**
 * Scroll chat to bottom
 */
function scrollToBottom() {
    const messagesDiv = document.getElementById('chatMessages');
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

/**
 * Generate unique session ID
 */
function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

/**
 * Search bus stops (for autocomplete - future feature)
 */
async function searchBusStops(query) {
    try {
        const response = await fetch(`${SEARCH_URL}?query=${encodeURIComponent(query)}`);
        const stops = await response.json();
        return stops;
    } catch (error) {
        console.error('Search error:', error);
        return [];
    }
}

function requestUserLocation() {
    if (!navigator.geolocation) {
        addMessage('❌ Geolocation is not supported by your browser.', 'bot');
        return;
    }
    
    showTypingIndicator();
    
    navigator.geolocation.getCurrentPosition(
        // Success callback
        async (position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            
            try {
                // Get nearby stops
                const response = await fetch(NEARBY_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        lat: lat,
                        lon: lon,
                        limit: 5
                    })
                });
                
                const nearbyStops = await response.json();
                
                removeTypingIndicator();
                
                if (nearbyStops.length === 0) {
                    addMessage('❌ No bus stops found nearby.', 'bot');
                } else {
                    addMessage(`📍 Found ${nearbyStops.length} bus stops near you:`, 'bot');
                    
                    // Format stops with distance
                    const stopsWithDistance = nearbyStops.map(stop => ({
                        ...stop,
                        description: `${stop.description} (${stop.distance}m away)`
                    }));
                    
                    addBusStopOptions(stopsWithDistance);
                }
                
            } catch (error) {
                console.error('Error fetching nearby stops:', error);
                removeTypingIndicator();
                addMessage('❌ Sorry, I couldn\'t fetch nearby bus stops.', 'bot');
            }
        },
        // Error callback
        (error) => {
            removeTypingIndicator();
            let errorMessage = '❌ ';
            
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    errorMessage += 'Location access denied. Please enable location permissions in your browser.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    errorMessage += 'Location information unavailable.';
                    break;
                case error.TIMEOUT:
                    errorMessage += 'Location request timed out.';
                    break;
                default:
                    errorMessage += 'An unknown error occurred.';
            }
            
            addMessage(errorMessage, 'bot');
        },
        // Options
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }
    );
}