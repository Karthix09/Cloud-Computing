// ==========================================
// Transport Buddy Chatbot - JavaScript
// ==========================================

class TransportBuddyChatbot {
    constructor() {
        this.messagesContainer = document.getElementById('chatMessages');
        this.userInput = document.getElementById('userInput');
        this.btnSend = document.getElementById('btnSend');
        this.btnNearby = document.getElementById('btnNearby');
        this.btnRouteHome = document.getElementById('btnRouteHome');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.sessionId = this.generateSessionId();
        this.init();
    }

    init() {
        // Event listeners
        this.btnSend.addEventListener('click', () => this.sendMessage());
        this.userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });
        this.btnNearby.addEventListener('click', () => this.getNearbyStops());
        this.btnRouteHome.addEventListener('click', () => {
            this.userInput.value = "how to get from home to orchard";
            this.sendMessage();
        });
        this.scrollToBottom();
    }

    generateSessionId() {
        return 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }

    // ==================== Send Message ====================
    async sendMessage() {
        const message = this.userInput.value.trim();
        if (!message) return;

        this.addMessage(message, 'user');
        this.userInput.value = '';
        this.showTyping();

        try {
            const response = await fetch('/api/chatbot/send-message', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    message: message,
                    sessionId: this.sessionId
                })
            });

            const data = await response.json();
            this.hideTyping();

            if (data.error) {
                this.addMessage(data.error, 'bot');
                return;
            }

            // Check if this is a route planning response
            if (data.routes) {
                this.renderRouteResponse(data);
            }
            // Regular Lex response
            else if (data.messages?.length) {
                data.messages.forEach(msg => this.addMessage(msg.content, 'bot'));
            }
            // Success message
            else if (data.message) {
                this.addMessage(data.message, 'bot');
            }

            // Structured data (bus stops, arrivals, etc.)
            if (data.data) {
                this.renderStructuredData(data.data);
            }

        } catch (error) {
            this.hideTyping();
            this.addMessage('Sorry, something went wrong. Please try again.', 'bot');
            console.error('Error:', error);
        }
    }

    // ==================== Add Message ====================
    addMessage(text, sender) {
        const wrapper = document.createElement('div');
        wrapper.className = sender === 'user'
            ? 'user-message-container'
            : 'bot-message-container';

        const bubble = document.createElement('div');
        bubble.className = sender === 'user'
            ? 'message-bubble user-message'
            : 'message-bubble bot-message';

        bubble.innerHTML = text.replace(/\n/g, "<br>");
        wrapper.appendChild(bubble);
        this.messagesContainer.appendChild(wrapper);
        this.scrollToBottom();
    }

    // ==================== Render Route Planning Response ====================
    renderRouteResponse(data) {
        const { origin, destination, routes, message } = data;
        
        const wrapper = document.createElement('div');
        wrapper.className = 'bot-message-container';
        
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble bot-message';
        
        let html = `
            <div class="route-response">
                <h3>✅ ${message}</h3>
                
                <div class="location-info">
                    <div class="location-card">
                        <strong>📍 From: ${origin.name}</strong>
                        ${origin.address ? `<div class="small-text">${origin.address}</div>` : ''}
                        <div class="bus-stop-info">
                            <strong>${origin.bus_stop.name}</strong> (${origin.bus_stop.code})
                            <br><small>📏 ${origin.bus_stop.distance}m away</small>
                        </div>
                    </div>
                    
                    <div class="location-card">
                        <strong>📍 To: ${destination.name}</strong>
                        ${destination.address ? `<div class="small-text">${destination.address}</div>` : ''}
                        <div class="bus-stop-info">
                            <strong>${destination.bus_stop.name}</strong> (${destination.bus_stop.code})
                            <br><small>📏 ${destination.bus_stop.distance}m away</small>
                        </div>
                    </div>
                </div>
                
                <div class="routes-container">
                    <h4>🚌 Suggested Routes (${routes.length} option${routes.length > 1 ? 's' : ''}):</h4>
        `;
        
        routes.forEach((route, index) => {
            const totalStops = route.legs.reduce((sum, leg) => sum + (leg.stops || 0), 0);
            const transfers = route.legs.length - 1;
            
            html += `
                <div class="route-option">
                    <div class="route-header">
                        <strong>Option ${index + 1} ${transfers > 0 ? `(${transfers} transfer${transfers > 1 ? 's' : ''})` : '(Direct)'}</strong>
                        <span class="eta-badge">⏱️ ${route.estimated_time_min || '~15'} min</span>
                    </div>
                    <div class="route-details">
            `;
            
            route.legs.forEach((leg, legIndex) => {
                html += `
                    <div class="route-leg">
                        ${legIndex > 0 ? '<div class="transfer-indicator">🔄 Transfer here</div>' : ''}
                        <div class="bus-service">
                            <span class="bus-number">${leg.service}</span>
                            <span class="stops-count">${leg.stops || 0} stop${(leg.stops || 0) !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="route-path">
                            ${leg.from} → ${leg.to}
                        </div>
                    </div>
                `;
            });
            
            html += `
                    </div>
                    <div class="small-text" style="margin-top: 8px; text-align: right;">
                        Total: ${totalStops} stop${totalStops !== 1 ? 's' : ''}
                    </div>
                </div>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
        
        bubble.innerHTML = html;
        wrapper.appendChild(bubble);
        this.messagesContainer.appendChild(wrapper);
        this.scrollToBottom();
    }

    // ==================== Render Structured Data ====================
    renderStructuredData(data) {
        if (data.type === "nearby_stops" || data.type === "multiple_stops") {
            this.renderBusStops(data.stops);
        }
        else if (data.type === "arrivals") {
            this.renderBusArrivals(data);
        }
    }

    // ==================== Render Bus Stops ====================
    renderBusStops(stops) {
        const wrapper = document.createElement("div");
        wrapper.className = "bot-message-container";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble bot-message";

        stops.forEach(stop => {
            const card = document.createElement("div");
            card.className = "bus-stop-card";
            card.onclick = () => this.getBusArrivals(stop.code);

            card.innerHTML = `
                <div class="bus-stop-code">🚏 ${stop.code}</div>
                <div class="bus-stop-name">${stop.description}</div>
                ${stop.distance ? `<div class="bus-stop-distance">📏 ${stop.distance}m away</div>` : ""}
            `;
            bubble.appendChild(card);
        });

        wrapper.appendChild(bubble);
        this.messagesContainer.appendChild(wrapper);
        this.scrollToBottom();
    }

    // ==================== Get Bus Arrivals ====================
    async getBusArrivals(code) {
        this.showTyping();
        try {
            const res = await fetch(`/api/chatbot/arrivals/${code}?sessionId=${this.sessionId}`);
            const data = await res.json();
            this.hideTyping();

            if (data.error) {
                this.addMessage(data.error, "bot");
                return;
            }

            this.renderBusArrivals(data);

        } catch (err) {
            this.hideTyping();
            this.addMessage("❌ Error fetching arrivals. Please try again.", "bot");
            console.error('Error:', err);
        }
    }

    // ==================== Render Bus Arrivals ====================
    renderBusArrivals(data) {
        const arrivals = data.arrivals;
        if (!arrivals?.services?.length) {
            this.addMessage(arrivals?.message || "No buses available at this stop.", "bot");
            return;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "bot-message-container";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble bot-message";

        arrivals.services.forEach(service => {
            const card = document.createElement("div");
            card.className = "bus-arrival-card";

            let html = `<div class="service-number">🚌 Service ${service.service_no}</div>`;

            service.buses.forEach(bus => {
                let minutes = bus.minutes_away;
                let timingClass = "timing-later";
                let timingText = `${minutes} min`;

                if (minutes <= 1) {
                    timingClass = "timing-arriving";
                    timingText = "Arriving";
                } else if (minutes <= 5) {
                    timingClass = "timing-soon";
                }

                let loadMap = {
                    SEA: ["load-sea", "Seats Available"],
                    SDA: ["load-sda", "Standing Available"],
                    LSD: ["load-lsd", "Limited Standing"]
                };
                let [loadClass, loadText] = loadMap[bus.load] || loadMap["SEA"];

                let typeMap = { 
                    SD: "Single Deck", 
                    DD: "Double Deck", 
                    BD: "Bendy" 
                };
                let busTypeText = typeMap[bus.type] || "";

                html += `
                    <div class="bus-timing">
                        <span class="timing-badge ${timingClass}">${timingText}</span>
                        <span class="load-indicator ${loadClass}">${loadText}</span>
                        ${busTypeText ? `<span class="bus-type">${busTypeText}</span>` : ''}
                    </div>
                `;
            });

            card.innerHTML = html;
            bubble.appendChild(card);
        });

        wrapper.appendChild(bubble);
        this.messagesContainer.appendChild(wrapper);
        this.scrollToBottom();
    }

    // ==================== Get Nearby Stops ====================
    async getNearbyStops() {
        if (!navigator.geolocation) {
            this.addMessage("❌ Geolocation is not supported by your browser.", "bot");
            return;
        }
        
        this.addMessage("📍 Getting your location…", "bot");
        this.showTyping();

        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                try {
                    const res = await fetch('/api/chatbot/nearby-stops', {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({
                            latitude: pos.coords.latitude,
                            longitude: pos.coords.longitude,
                            sessionId: this.sessionId
                        })
                    });

                    const data = await res.json();
                    this.hideTyping();

                    if (data.error) {
                        this.addMessage(data.error, "bot");
                        return;
                    }

                    if (data.type === 'nearby_stops') {
                        this.addMessage(`✅ Found ${data.stops.length} nearby stop${data.stops.length !== 1 ? 's' : ''}:`, "bot");
                        this.renderBusStops(data.stops);
                    }

                } catch (err) {
                    this.hideTyping();
                    this.addMessage("❌ Unable to load nearby stops. Please try again.", "bot");
                    console.error('Error:', err);
                }
            },
            (error) => {
                this.hideTyping();
                let errorMsg = "❌ Location access denied.";
                if (error.code === 1) {
                    errorMsg = "❌ Please allow location access to find nearby stops.";
                } else if (error.code === 2) {
                    errorMsg = "❌ Location information unavailable.";
                } else if (error.code === 3) {
                    errorMsg = "❌ Location request timed out.";
                }
                this.addMessage(errorMsg, "bot");
            }
        );
    }

    // ==================== UI Helpers ====================
    scrollToBottom() {
        setTimeout(() => {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }, 100);
    }

    showTyping() { 
        this.typingIndicator.style.display = 'flex';
        this.scrollToBottom();
    }
    
    hideTyping() { 
        this.typingIndicator.style.display = 'none'; 
    }
}

// Initialize chatbot when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    new TransportBuddyChatbot();
});