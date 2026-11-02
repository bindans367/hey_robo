(() => {
  const face = document.querySelector(".face");
  const eyes = [...document.querySelectorAll(".eye")];
  const stateLabel = document.querySelector("#state-label");
  const connectionLabel = document.querySelector("#connection-label");
  const fullButton = document.querySelector("#fullscreen");
  let current = "offline";
  let lastActivity = 0;
  let hideTimer;

  function blink(allowDouble = true) {
    // Normally blink both eyes together. A few blinks are slightly staggered,
    // and occasional double blinks keep the movement from feeling clockwork.
    const staggered = Math.random() < 0.1;
    eyes.forEach((eye, index) => {
      const delay = staggered && index === 1 ? 65 : 0;
      window.setTimeout(() => {
        eye.classList.remove("blinking");
        void eye.offsetWidth;
        eye.classList.add("blinking");
        window.setTimeout(() => eye.classList.remove("blinking"), 260);
      }, delay);
    });
    if (allowDouble && Math.random() < 0.1) window.setTimeout(() => blink(false), 300);
  }

  function scheduleBlink() {
    const delay = current === "sleeping" ? 3900 + Math.random() * 3800 : 3200 + Math.random() * 3300;
    window.setTimeout(() => {
      blink();
      scheduleBlink();
    }, delay);
  }

  function showState(state, label, online = true) {
    current = state;
    document.body.dataset.state = state;
    stateLabel.textContent = label;
    connectionLabel.textContent = online ? "BRAIN CONNECTED" : "BRAIN OFFLINE";
    face.style.setProperty("--glow", state === "speaking" ? "#a28cff" : state === "offline" ? "#8995a9" : "#71c9ff");
  }

  function handleStatus(data) {
    const robot = data?.robot || {};
    const activity = robot.activity || {};
    const phase = String(activity.phase || (robot.running ? "READY" : "STOPPED")).toUpperCase();
    const detail = String(activity.detail || "").toLowerCase();
    const now = Date.now();
    if (activity.updated_at) lastActivity = Date.parse(activity.updated_at) || now;
    const fresh = !lastActivity || now - lastActivity < 15000;

    // The dashboard can speak a script even when the hands-free bot is stopped.
    // Honor those live speech phases, then use process state for idle/listening.
    if (phase === "SPEAKING" && (robot.running || fresh)) return showState("speaking", "Robo is speaking");
    if ((phase === "THINKING" || phase === "TRANSCRIPT") && robot.running) return showState("thinking", "Robo is thinking");
    if ((phase === "GREETING" || phase === "STARTING") && robot.running) return showState("waking", phase === "GREETING" ? "Robo is saying hello" : "Robo is waking up");
    if (!robot.running || phase === "STOPPED") return showState("offline", "Robo is resting", false);
    if (!fresh && phase !== "LISTENING") return showState("offline", "Robo is resting", false);
    if (phase === "INTERRUPTING" || phase === "INTERRUPTED") return showState("listening", "Robo is ready");
    if (phase === "LISTENING" && /wake phrase|listening for hey robo|listening for .+ or a sit question/.test(detail)) {
      return showState("sleeping", "Say “Hey Robo” to wake me");
    }
    if (phase === "READY" && /sleeping|say hey robo/.test(detail)) return showState("sleeping", "Say “Hey Robo” to wake me");
    if (phase === "LISTENING" || phase === "READY") return showState("listening", "Robo is listening");
    showState("offline", "Robo is resting", false);
  }

  async function poll() {
    try {
      const response = await fetch("/api/status", {cache: "no-store"});
      if (!response.ok) throw new Error("status unavailable");
      handleStatus(await response.json());
    } catch (_) {
      showState("offline", "Waiting for Robo Brain", false);
    } finally {
      window.setTimeout(poll, 400);
    }
  }

  async function toggleFullscreen() {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch (_) {
      stateLabel.textContent = "Use your browser’s full-screen button";
    }
  }

  function revealControls() {
    face.classList.remove("hide-ui");
    clearTimeout(hideTimer);
    hideTimer = window.setTimeout(() => face.classList.add("hide-ui"), 4500);
  }

  fullButton.addEventListener("click", toggleFullscreen);
  document.addEventListener("keydown", event => {
    if (event.key.toLowerCase() === "f" && !event.ctrlKey && !event.altKey) toggleFullscreen();
    if (event.key === "Escape") revealControls();
  });
  document.addEventListener("fullscreenchange", () => {
    fullButton.innerHTML = document.fullscreenElement ? "⛶ <span>EXIT FULL SCREEN</span>" : "⛶ <span>FULL SCREEN</span>";
  });
  document.addEventListener("pointermove", revealControls, {passive: true});
  document.addEventListener("pointerdown", revealControls, {passive: true});
  scheduleBlink();
  poll();
})();
