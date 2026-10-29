document.querySelector(".send-btn").addEventListener("click", async () => {
    const inputField = document.querySelector(".glass-input");
    const message = inputField.value.trim();
    if (!message) return;

    // Chat log-e user message add korun
    const chatLog = document.querySelector(".chat-log");
    chatLog.innerHTML += `<p><strong>YOU •</strong> ${message}</p>`;
    inputField.value = "";

    try {
        // Python backend-er kache request pathano
        const response = await fetch("http://localhost:5000/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ message: message })
        });

        const data = await response.json();
        
        // Python theke pawa response chat-e dekhano
        chatLog.innerHTML += `<p><strong>ORBIT •</strong> ${data.response}</p>`;
        chatLog.scrollTop = chatLog.scrollHeight;
        
    } catch (error) {
        console.error("Backend error:", error);
    }
});