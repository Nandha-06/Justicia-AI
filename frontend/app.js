// State Variables
let chatHistory = [];
let statusInterval = null;
let activeAbortController = null;

// Initialize Page
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide Icons
    lucide.createIcons();
    
    // Auto-adjust textarea height
    const textarea = document.getElementById("user-input");
    textarea.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = (this.scrollHeight) + "px";
    });

    // Initial Status Check & Start Polling
    fetchStatus();
    statusInterval = setInterval(fetchStatus, 2500);
});

// Fetch Backend Pipeline Status
async function fetchStatus() {
    try {
        const response = await fetch("/api/status");
        if (!response.ok) throw new Error("Status failed");
        
        const data = await response.json();
        
        // 1. Update API Key Connection Status
        const apiKeyBadge = document.getElementById("api-key-status");
        if (data.api_key_configured) {
            apiKeyBadge.className = "badge badge-success";
            apiKeyBadge.innerHTML = '<span class="indicator"></span>Gemma Ready';
        } else {
            apiKeyBadge.className = "badge badge-error";
            apiKeyBadge.innerHTML = '<span class="indicator"></span>API Key Missing';
        }
        
        // 2. Update Scraper Status
        const scraperBadge = document.getElementById("scraper-status-text");
        const scrapeBtn = document.getElementById("btn-scrape");
        const scrapeProgress = document.getElementById("scrape-progress");
        const scrapeProgressText = document.getElementById("scrape-progress-text");
        
        const scrapedPct = (data.scraped_count / data.scraped_total) * 100;
        scrapeProgress.style.width = `${scrapedPct}%`;
        scrapeProgressText.innerText = `${data.scraped_count} / ${data.scraped_total} sections collected`;
        
        if (data.is_scraping) {
            scraperBadge.className = "badge badge-warning";
            scraperBadge.innerHTML = '<span class="indicator"></span>Scraping BNS...';
            scrapeBtn.disabled = true;
            scrapeBtn.innerHTML = '<i class="spinner"></i> Scraping...';
        } else {
            if (data.scraped_count === data.scraped_total) {
                scraperBadge.className = "badge badge-success";
                scraperBadge.innerHTML = '<span class="indicator"></span>Complete';
                scrapeBtn.disabled = false;
                scrapeBtn.innerHTML = '<i data-lucide="refresh-cw"></i> Re-collect Data';
            } else {
                scraperBadge.className = "badge badge-warning";
                scraperBadge.innerHTML = '<span class="indicator"></span>Incomplete';
                scrapeBtn.disabled = false;
                scrapeBtn.innerHTML = '<i data-lucide="download-cloud"></i> Collect Law Data';
            }
        }
        
        // 3. Update Vector Database Ingestion Status
        const dbBadge = document.getElementById("db-status-text");
        const ingestBtn = document.getElementById("btn-ingest");
        
        if (data.is_ingesting) {
            dbBadge.className = "badge badge-warning";
            dbBadge.innerHTML = '<span class="indicator"></span>Building...';
            ingestBtn.disabled = true;
            ingestBtn.innerHTML = '<i class="spinner"></i> Ingesting...';
        } else {
            if (data.db_loaded) {
                dbBadge.className = "badge badge-success";
                dbBadge.innerHTML = '<span class="indicator"></span>Ready';
                ingestBtn.disabled = false;
                ingestBtn.innerHTML = '<i data-lucide="database"></i> Rebuild Index';
            } else {
                dbBadge.className = "badge badge-error";
                dbBadge.innerHTML = '<span class="indicator"></span>Not Indexed';
                // Only enable ingestion if data has been scraped
                ingestBtn.disabled = (data.scraped_count === 0);
                ingestBtn.innerHTML = '<i data-lucide="database"></i> Build Vector Index';
            }
        }
        
        // Recreate icons in updated status buttons
        lucide.createIcons();
        
    } catch (error) {
        console.error("Error fetching status:", error);
    }
}

// Trigger Law Data Crawling API
async function triggerScrape() {
    try {
        const response = await fetch("/api/trigger-scrape", { method: "POST" });
        if (response.ok) {
            fetchStatus();
        }
    } catch (error) {
        console.error("Error triggering scrape:", error);
    }
}

// Trigger Vector Store Ingestion API
async function triggerIngest() {
    try {
        const response = await fetch("/api/trigger-ingest", { method: "POST" });
        if (response.ok) {
            fetchStatus();
        }
    } catch (error) {
        console.error("Error triggering ingestion:", error);
    }
}

// Helper to Format Message Text to HTML using Marked.js
function formatMarkdown(text) {
    if (!text) return "";
    
    // Clean up LaTeX math formatting for arrows
    let cleanedText = text;
    cleanedText = cleanedText.replace(/\$\s*\\(rightarrow|to)\s*\$/g, " → ");
    cleanedText = cleanedText.replace(/\$\s*\\implies\s*\$/g, " ⇒ ");
    cleanedText = cleanedText.replace(/\\(rightarrow|to)/g, " → ");
    cleanedText = cleanedText.replace(/\\implies/g, " ⇒ ");
    
    // Parse using marked library
    let html = marked.parse(cleanedText);
    
    // Convert regular links to styled citation tags with Lucide icons
    html = html.replace(/<a\s+href="([^"]+)">([\s\S]*?)<\/a>/g, (match, href, linkText) => {
        return `<a href="${href}" target="_blank" class="citation-tag"><i data-lucide="external-link"></i> ${linkText}</a>`;
    });
    
    return html;
}

// Extract Citations for a Row of Dedicated Badges
function extractCitations(text) {
    const regex = /\[(.*?)\]\((https?:\/\/devgan\.in\/bns\/.*?)\)/g;
    const citations = [];
    let match;
    const seen = new Set();
    
    while ((match = regex.exec(text)) !== null) {
        const title = match[1];
        const url = match[2];
        if (!seen.has(url)) {
            citations.push({ title, url });
            seen.add(url);
        }
    }
    return citations;
}

// Append Message to Chat Window
function appendMessage(role, content, steps = []) {
    const container = document.getElementById("messages-container");
    
    // Remove welcome box if present
    const welcomeBox = container.querySelector(".welcome-box");
    if (welcomeBox) {
        container.removeChild(welcomeBox);
    }
    
    const messageDiv = document.createElement("div");
    messageDiv.className = `message message-${role}`;
    
    // Avatar
    const avatarDiv = document.createElement("div");
    avatarDiv.className = "message-avatar";
    avatarDiv.innerHTML = role === "user" ? '<i data-lucide="user"></i>' : '<i data-lucide="scale"></i>';
    
    // Content Wrap
    const contentWrap = document.createElement("div");
    contentWrap.className = "message-content";
    
    // Bubble
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    
    if (role === "user") {
        bubble.innerText = content;
    } else {
        bubble.innerHTML = formatMarkdown(content);
    }
    contentWrap.appendChild(bubble);
    
    // Add Reasoning Steps (Collapsible accordion for agent actions)
    if (role === "assistant" && steps && steps.length > 0) {
        const reasoningDiv = document.createElement("div");
        reasoningDiv.className = "reasoning-container collapsed";
        
        let stepsLogs = "";
        steps.forEach((step, idx) => {
            stepsLogs += `[Step ${idx + 1}] Executing: ${step.tool}\n`;
            stepsLogs += `Input parameters: ${JSON.stringify(step.tool_input)}\n`;
            if (step.log) {
                stepsLogs += `Agent reasoning: ${step.log.trim()}\n`;
            }
            stepsLogs += `Retrieved observation length: ${step.observation_length} characters\n`;
            stepsLogs += `--------------------------------------------------\n`;
        });
        
        reasoningDiv.innerHTML = `
            <div class="reasoning-header" onclick="toggleReasoning(this)">
                <div class="reasoning-header-left">
                    <i data-lucide="brain-circuit"></i>
                    <span>Agent Retrieval Steps (${steps.length} tool calls)</span>
                </div>
                <i data-lucide="chevron-down" class="chevron"></i>
            </div>
            <pre class="reasoning-body">${stepsLogs.trim()}</pre>
        `;
        contentWrap.appendChild(reasoningDiv);
    }
    
    // Add Dedicated Citation Badges at the bottom of AI Bubble
    if (role === "assistant") {
        const citations = extractCitations(content);
        if (citations.length > 0) {
            const badgesRow = document.createElement("div");
            badgesRow.className = "citation-badges-row";
            citations.forEach(cit => {
                const badgeLink = document.createElement("a");
                badgeLink.className = "citation-tag";
                badgeLink.href = cit.url;
                badgeLink.target = "_blank";
                badgeLink.innerHTML = `<i data-lucide="bookmark-check"></i> ${cit.title}`;
                badgesRow.appendChild(badgeLink);
            });
            contentWrap.appendChild(badgesRow);
        }
    }
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentWrap);
    container.appendChild(messageDiv);
    
    // Refresh Icons inside appended element
    lucide.createIcons();
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Toggle Collapsible Reasoning Panel
function toggleReasoning(headerElem) {
    const container = headerElem.parentElement;
    container.classList.toggle("collapsed");
}

// Show/Remove Thinking/Loading Bubble
function showThinking() {
    const container = document.getElementById("messages-container");
    const thinkingDiv = document.createElement("div");
    thinkingDiv.className = "message message-assistant thinking-bubble-container";
    thinkingDiv.id = "thinking-bubble";
    
    thinkingDiv.innerHTML = `
        <div class="message-avatar">
            <i data-lucide="scale"></i>
        </div>
        <div class="message-content">
            <div class="message-bubble thinking-bubble">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
            </div>
        </div>
    `;
    container.appendChild(thinkingDiv);
    lucide.createIcons();
    container.scrollTop = container.scrollHeight;
}

function removeThinking() {
    const elem = document.getElementById("thinking-bubble");
    if (elem) {
        elem.parentElement.removeChild(elem);
    }
}

// Send user query to API with streaming support
async function sendQuery(text = null) {
    // If active request is running, clicking this button stops it
    if (activeAbortController) {
        stopQuery();
        return;
    }

    const input = document.getElementById("user-input");
    const query = text || input.value.trim();
    if (!query) return;
    
    if (!text) {
        input.value = "";
        input.style.height = "auto";
    }
    
    // Append User bubble
    appendMessage("user", query);
    
    // Append Loading bubble
    showThinking();

    // Create AbortController to support Stop functionality
    activeAbortController = new AbortController();
    setButtonToStopState();
    
    try {
        const response = await fetch("/api/query-stream", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                query: query,
                chat_history: chatHistory
            }),
            signal: activeAbortController.signal
        });
        
        removeThinking();
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Query failed");
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let fullAnswer = "";
        let streamSteps = [];
        
        // Append an empty assistant bubble to stream into
        const bubbleElements = appendEmptyAssistantBubble();
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop(); // Keep partial line in buffer
            
            for (const line of lines) {
                const trimmedLine = line.trim();
                if (trimmedLine.startsWith("data: ")) {
                    const dataStr = trimmedLine.slice(6).trim();
                    if (!dataStr) continue;
                    try {
                        const data = JSON.parse(dataStr);
                        if (data.type === "token") {
                            fullAnswer += data.content;
                            updateAssistantBubble(bubbleElements, fullAnswer, streamSteps);
                        } else if (data.type === "tool_start") {
                            streamSteps.push({
                                tool: data.tool,
                                tool_input: data.tool_input,
                                log: `Agent calling search tool...`,
                                observation_length: 0
                            });
                            updateAssistantBubble(bubbleElements, fullAnswer, streamSteps);
                        } else if (data.type === "tool_end") {
                            const step = streamSteps.find(s => s.tool === data.tool && s.observation_length === 0);
                            if (step) {
                                step.observation_length = data.observation_length;
                                step.log = `Search tool successfully returned ${data.observation_length} characters.`;
                            }
                            updateAssistantBubble(bubbleElements, fullAnswer, streamSteps);
                        } else if (data.type === "error") {
                            throw new Error(data.error);
                        }
                    } catch (e) {
                        console.error("Error parsing stream chunk:", e);
                    }
                }
            }
        }
        
        // Save history (user and assistant messages)
        chatHistory.push({ role: "user", content: query });
        chatHistory.push({ role: "assistant", content: fullAnswer });
        
        // Keep history bounded to 10 entries to conserve context size
        if (chatHistory.length > 10) {
            chatHistory = chatHistory.slice(chatHistory.length - 10);
        }
        
    } catch (error) {
        removeThinking();
        if (error.name === 'AbortError') {
            appendMessage("assistant", "Generation stopped by user.");
        } else {
            appendMessage("assistant", `Error: ${error.message}. Make sure your GEMINI_API_KEY environment variable is configured properly and that you've indexed your data.`);
        }
    } finally {
        activeAbortController = null;
        setButtonToSendState();
    }
}

// Toggle Send button states and cancel request
function setButtonToStopState() {
    const btn = document.getElementById("btn-send");
    if (btn) {
        btn.className = "btn-send btn-stop";
        btn.innerHTML = '<i data-lucide="square"></i>';
        btn.title = "Stop Generation";
        lucide.createIcons();
    }
}

function setButtonToSendState() {
    const btn = document.getElementById("btn-send");
    if (btn) {
        btn.className = "btn-send";
        btn.innerHTML = '<i data-lucide="send"></i>';
        btn.title = "Send Query";
        lucide.createIcons();
    }
}

function stopQuery() {
    if (activeAbortController) {
        activeAbortController.abort();
    }
}

// Append Empty Assistant Bubble for streaming
function appendEmptyAssistantBubble() {
    const container = document.getElementById("messages-container");
    
    // Remove welcome box if present
    const welcomeBox = container.querySelector(".welcome-box");
    if (welcomeBox) {
        container.removeChild(welcomeBox);
    }
    
    const messageDiv = document.createElement("div");
    messageDiv.className = "message message-assistant";
    
    const avatarDiv = document.createElement("div");
    avatarDiv.className = "message-avatar";
    avatarDiv.innerHTML = '<i data-lucide="scale"></i>';
    
    const contentWrap = document.createElement("div");
    contentWrap.className = "message-content";
    
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>'; // Initial thinking dots
    
    contentWrap.appendChild(bubble);
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentWrap);
    container.appendChild(messageDiv);
    
    lucide.createIcons();
    container.scrollTop = container.scrollHeight;
    
    return {
        messageDiv: messageDiv,
        contentWrap: contentWrap,
        bubble: bubble
    };
}

// Update Assistant Bubble during streaming
function updateAssistantBubble(elements, content, steps = []) {
    const container = document.getElementById("messages-container");
    const { contentWrap, bubble } = elements;
    
    // 1. Update text bubble content
    if (content) {
        bubble.innerHTML = formatMarkdown(content);
    } else {
        if (steps.length > 0) {
            bubble.innerHTML = `<div class="streaming-status"><i class="spinner"></i> Searching legal database...</div>`;
        }
    }
    
    // 2. Update reasoning steps panel
    let reasoningDiv = contentWrap.querySelector(".reasoning-container");
    if (steps && steps.length > 0) {
        if (!reasoningDiv) {
            reasoningDiv = document.createElement("div");
            reasoningDiv.className = "reasoning-container collapsed";
            contentWrap.appendChild(reasoningDiv);
        }
        
        let stepsLogs = "";
        steps.forEach((step, idx) => {
            stepsLogs += `[Step ${idx + 1}] Executing: ${step.tool}\n`;
            if (step.tool_input) {
                stepsLogs += `Input parameters: ${JSON.stringify(step.tool_input)}\n`;
            }
            if (step.log) {
                stepsLogs += `Status: ${step.log}\n`;
            }
            if (step.observation_length) {
                stepsLogs += `Retrieved observation length: ${step.observation_length} characters\n`;
            }
            stepsLogs += `--------------------------------------------------\n`;
        });
        
        reasoningDiv.innerHTML = `
            <div class="reasoning-header" onclick="toggleReasoning(this)">
                <div class="reasoning-header-left">
                    <i data-lucide="brain-circuit"></i>
                    <span>Agent Retrieval Steps (${steps.length} tool calls)</span>
                </div>
                <i data-lucide="chevron-down" class="chevron"></i>
            </div>
            <pre class="reasoning-body">${stepsLogs.trim()}</pre>
        `;
    }
    
    // 3. Update dedicated citations badges row
    if (content) {
        const citations = extractCitations(content);
        let badgesRow = contentWrap.querySelector(".citation-badges-row");
        
        if (citations.length > 0) {
            if (!badgesRow) {
                badgesRow = document.createElement("div");
                badgesRow.className = "citation-badges-row";
                contentWrap.appendChild(badgesRow);
            } else {
                badgesRow.innerHTML = ""; // Clear old tags
            }
            
            citations.forEach(cit => {
                const badgeLink = document.createElement("a");
                badgeLink.className = "citation-tag";
                badgeLink.href = cit.url;
                badgeLink.target = "_blank";
                badgeLink.innerHTML = `<i data-lucide="bookmark-check"></i> ${cit.title}`;
                badgesRow.appendChild(badgeLink);
            });
        } else if (badgesRow) {
            contentWrap.removeChild(badgesRow);
        }
    }
    
    lucide.createIcons();
    container.scrollTop = container.scrollHeight;
}

// Send suggested prompt chip
function sendQuickPrompt(promptText) {
    sendQuery(promptText);
}

// Enter Key handler
function handleKeyPress(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendQuery();
    }
}

// Clear Chat conversation history
function clearChat() {
    chatHistory = [];
    const container = document.getElementById("messages-container");
    container.innerHTML = `
        <div class="welcome-box">
            <div class="welcome-icon">
                <i data-lucide="gavel"></i>
            </div>
            <h3>Justicia AI</h3>
            <p>I am a RAG-powered agent connected to a high-speed local <strong>TurboVec</strong> vector store containing the entire text of the new <strong>Bharatiya Nyaya Sanhita (BNS), 2023</strong>. I use <strong>gemma-4-31b-it</strong> to analyze queries, search the code, and cite proof-verified answers.</p>
            
            <div class="quick-prompts-header">Try asking me:</div>
            <div class="quick-prompts">
                <button class="prompt-chip" onclick="sendQuickPrompt('What is Section 302 of the IPC (murder) replaced by in the new BNS?')">
                    <i data-lucide="arrow-right"></i> What replaces IPC Section 302?
                </button>
                <button class="prompt-chip" onclick="sendQuickPrompt('What is the definition and punishment for theft in BNS?')">
                    <i data-lucide="arrow-right"></i> Definition & punishment of theft
                </button>
                <button class="prompt-chip" onclick="sendQuickPrompt('Explain how good faith is defined under the General Explanations of BNS.')">
                    <i data-lucide="arrow-right"></i> How is 'good faith' defined?
                </button>
                <button class="prompt-chip" onclick="sendQuickPrompt('What are the categories of punishments under Section 4 of BNS?')">
                    <i data-lucide="arrow-right"></i> List punishments under Section 4
                </button>
            </div>
        </div>
    `;
    lucide.createIcons();
}

// Toggle Collapsible Developer Pipeline Tools drawer in Sidebar
function togglePipelineTools() {
    const controls = document.getElementById("pipeline-admin-controls");
    const chevron = document.getElementById("pipeline-chevron");
    controls.classList.toggle("collapsed");
    if (controls.classList.contains("collapsed")) {
        chevron.style.transform = "rotate(0deg)";
    } else {
        chevron.style.transform = "rotate(90deg)";
    }
}
