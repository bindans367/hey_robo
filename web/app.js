const state = { knowledge: [], history: [], categories: [], scripts: [], activeScriptId: "", settings: null, backendOnline: false, cloudMode: false, browserVoiceActive: false, browserVoicePhase: "STOPPED" };
const $ = (selector) => document.querySelector(selector);
const esc = (value = "") => String(value).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const pretty = value => String(value || "general").replace(/[_-]+/g, " ").replace(/\b\w/g, c => c.toUpperCase());
let toastTimer;

async function api(path, body) {
  let response;
  try {
    response = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
  } catch (_) {
    setBackendConnection(false);
    throw new Error("Robo Brain is not running. Start it with .\\venv\\Scripts\\python.exe robo_brain.py and retry.");
  }
  setBackendConnection(true);
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}
function setBackendConnection(online) {
  state.backendOnline = online;
  const banner = $("#connection-banner");
  if (!banner) return;
  banner.classList.toggle("hidden", online);
  $("#connection-message").textContent = online
    ? "Robo Brain is connected."
    : "Robo Brain is offline. Start the local Python server to use chat, settings, voice, and history.";
}
function toast(message, bad=false) {
  const el = $("#toast"); el.textContent = message; el.className = `toast show${bad ? " bad" : ""}`;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.className = "toast", 3200);
}
function setBusy(button, busy, label) {
  if (busy) { button.dataset.oldText = button.innerHTML; button.disabled = true; button.innerHTML = `<span class="spinner"></span> ${label || "Working…"}`; }
  else { button.disabled = false; if (button.dataset.oldText) button.innerHTML = button.dataset.oldText; }
}
function speakInBrowser(text) {
  if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) return Promise.resolve(false);
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(String(text || "").trim());
  const voice = state.settings?.voice || {};
  utterance.lang = "en-IN";
  utterance.rate = Math.max(.65, Math.min(1.4, Number(voice.speed) || 1));
  utterance.pitch = Math.max(.5, Math.min(2, 1 + (Number(voice.pitch) || 0) / 10));
  utterance.volume = Math.max(0, Math.min(1, Number.isFinite(Number(voice.volume)) ? Number(voice.volume) / 100 : 1));
  const gender = String(voice.gender || "").toLowerCase();
  const voices = window.speechSynthesis.getVoices();
  utterance.voice = voices.find(item => /^en[-_]in$/i.test(item.lang) && (!gender || item.name.toLowerCase().includes(gender)))
    || voices.find(item => /^en[-_]in$/i.test(item.lang)) || null;
  return new Promise(resolve => {
    utterance.onend = () => resolve(true);
    utterance.onerror = () => resolve(false);
    try { window.speechSynthesis.speak(utterance); } catch { resolve(false); }
  });
}
async function speakText(text) {
  const result = await api("/api/speak", {text});
  if (result.speech_mode === "browser" && !await speakInBrowser(text)) {
    throw new Error("This browser does not have speech output available.");
  }
  return result;
}
function go(page) {
  document.querySelectorAll(".page").forEach(x => x.classList.toggle("active", x.id === `page-${page}`));
  document.querySelectorAll(".nav-item").forEach(x => x.classList.toggle("active", x.dataset.page === page));
  const title = {overview:"Overview",knowledge:"Knowledge base",speak:"Script to speech",history:"Conversation history",settings:"Voice & AI settings"}[page] || "Overview";
  $("#crumb-page").textContent = title;
  if (page === "history") refreshHistory();
  if (page === "knowledge") renderKnowledge();
  window.scrollTo({top:0,behavior:"smooth"});
}
function applySettings(settings) {
  state.settings = settings;
  window.dispatchEvent(new CustomEvent("robo-settings-applied", {detail: settings}));
  const isOnline = settings.mode === "online";
  const modeLabel = isOnline ? "Online · Gemini AI" : settings.mode === "local" ? "Local Qwen AI" : "Offline SIT brain";
  $("#mode-badge").innerHTML = `<i></i> ${modeLabel}`;
  $("#mode-badge").classList.toggle("online", isOnline);
  $("#mode-badge").title = isOnline ? "Current: Online (Gemini AI) — Click to switch to Offline" : "Current: Offline — Click to switch to Online";
  const voice = settings.voice || {};
  const selectedVoiceId = voice.provider === "system" ? "system" : `${voice.provider || "edge"}:${voice.voice_id || "en-IN-NeerjaNeural"}`;
  if (![...$("#tts-voice").options].some(option => option.value === selectedVoiceId)) {
    const option = new Option(`${selectedVoiceId} · ${voice.gender || "female"}`, selectedVoiceId);
    option.dataset.gender = voice.gender || "female";
    $("#tts-voice").add(option);
  }
  $("#tts-voice").value = selectedVoiceId;
  $("#tts-style").value = voice.style || "indian_clear";
  $("#speed-range").value = voice.speed ?? 1;
  $("#pitch-range").value = voice.pitch ?? 0;
  $("#volume-range").value = voice.volume ?? 100;
  updateRangeLabels();
  const online = settings.online || {};
  $("#online-url").value = online.base_url || "https://generativelanguage.googleapis.com/v1beta/openai";
  $("#online-model").value = online.model || "gemini-3.8-flash";
  $("#cloud-provider").value = /generativelanguage\.googleapis\.com/i.test(online.base_url || "") ? "gemini" : "custom";
  $("#online-key").value = "";
  $("#key-status").textContent = online.api_key_set ? "A key is saved on this device. Leave blank to keep it." : "No key saved yet.";
  const local = settings.local_llm || {};
  $("#local-url").value = local.base_url || "http://127.0.0.1:11434/v1";
  $("#local-model").value = local.model || "qwen3:0.6b";
  $("#local-key").value = "";
  $("#local-key-status").textContent = local.api_key_set ? "A local server key is saved. Leave blank to keep it." : "No local key saved; Ollama normally needs none.";
  $("#system-prompt").value = settings.system_prompt || "";
  const flow = settings.conversation || {}, mic = settings.microphone || {};
  $("#welcome-text").value = flow.welcome || "";
  $("#wake-phrases").value = (flow.wake_phrases || []).join("\n");
  $("#stop-phrases").value = (flow.stop_phrases || []).join("\n");
  $("#farewell-text").value = flow.farewell || "";
  $("#thank-reply").value = flow.thank_reply || "";
  $("#no-match-reply").value = flow.no_match_reply || "";
  $("#pause-reply").value = flow.pause_reply || "";
  $("#listen-timeout").value = flow.listen_timeout ?? 8;
  $("#phrase-limit").value = flow.phrase_time_limit ?? 15;
  $("#sleep-after-answer").value = flow.sleep_after_answer ?? 2;
  $("#mic-device").value = mic.device_index ?? -1;
  $("#mic-threshold").value = mic.energy_threshold ?? 300;
  $("#transcription-provider").value = mic.transcription_provider || "auto";
  $("#robo-mood").value = flow.mood || "friendly";
  $("#humor-enabled").checked = Boolean(flow.humor_enabled);
  $("#humor-frequency").value = flow.humor_frequency ?? 5;
  document.querySelectorAll("input[name=answer-mode]").forEach(r => r.checked = r.value === settings.mode);
  toggleOnlineFields();
  updateSpeechLabels();
}
function updateRangeLabels() {
  const speed = Number($("#speed-range").value), pitch = Number($("#pitch-range").value), volume = Number($("#volume-range").value);
  $("#speed-value").textContent = `${speed.toFixed(2).replace(/0$/,"")}×`;
  $("#pitch-value").textContent = pitch === 0 ? "Neutral" : `${pitch > 0 ? "+" : ""}${pitch}`;
  $("#volume-value").textContent = `${volume}%`;
  $("#stat-voice-detail").textContent = `${speed < .9 ? "Slow and clear" : speed > 1.15 ? "Brisk pace" : "Natural pace"} · ${pitch === 0 ? "neutral tone" : pitch < 0 ? "lower tone" : "higher tone"}`;
  $("#stat-voice").textContent = $("#tts-voice")?.selectedOptions[0]?.textContent.split("·")[0].trim() || "Neerja";
  updateSpeechLabels();
}
function updateSpeechLabels() {
  const voiceName = $("#tts-voice")?.selectedOptions[0]?.textContent.split("·")[0].trim() || "Neerja";
  const speed = Number($("#speed-range")?.value || 1);
  if ($("#speech-voice-name")) $("#speech-voice-name").textContent = voiceName + " voice";
  if ($("#speech-speed-name")) $("#speech-speed-name").textContent = speed < .9 ? "Slower pace" : speed > 1.15 ? "Faster pace" : "Natural pace";
}
function toggleOnlineFields() {
  const mode = document.querySelector("input[name=answer-mode]:checked")?.value || "offline";
  const online = mode === "online", local = mode === "local";
  $("#online-fields").classList.toggle("hidden", !online);
  $("#local-fields").classList.toggle("hidden", !local);
  $("#offline-note").classList.toggle("hidden", online || local);
}
function renderKnowledge() {
  const query = $("#knowledge-search").value.trim().toLowerCase();
  const category = $("#category-filter").value;
  const rows = state.knowledge.filter(item => (!category || item.category === category) && (!query || [item.title,item.answer,item.id,...(item.keywords||[])].join(" ").toLowerCase().includes(query)));
  $("#knowledge-nav-count").textContent = state.knowledge.length;
  $("#stat-knowledge").textContent = state.knowledge.length.toLocaleString();
  $("#result-count").textContent = `${rows.length} answer${rows.length===1?"":"s"}`;
  $("#knowledge-empty").classList.toggle("hidden", rows.length > 0);
  $("#knowledge-rows").innerHTML = rows.map(item => `<tr>
    <td><div class="topic-cell"><span class="topic-dot"></span><div><strong>${esc(item.title)}</strong><small>${esc(item.id)}</small></div></div></td>
    <td><div class="answer-preview">${esc(item.answer)}</div><span class="category-chip">${esc(pretty(item.category))}</span></td>
    <td><span class="trigger-list">${esc((item.keywords||[]).slice(0,2).join(" · "))}${(item.keywords||[]).length>2?` <b>+${item.keywords.length-2}</b>`:""}</span></td>
    <td><div class="row-actions"><button class="row-button edit-entry" data-id="${esc(item.id)}" title="Edit">✎</button><button class="row-button delete-entry" data-id="${esc(item.id)}" title="Delete">×</button></div></td></tr>`).join("");
}
function renderHistory() {
  const events = state.history;
  const content = events.length ? events.map(event => {
    const script = event.kind === "script";
    const time = event.time ? new Date(event.time).toLocaleString([], {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) : "";
    return `<article class="history-item"><div class="history-symbol ${script?"script-symbol":""}">${script?"◖":"?"}</div><div class="history-body"><div class="history-item-head"><span class="history-kind">${script?"SCRIPT SPOKEN":"QUESTION"}</span><time>${esc(time)}</time><span class="history-mode">${esc(pretty(event.source || "robot"))}</span></div><p class="history-question">${esc(event.text)}</p>${script?"":`<p class="history-answer"><span>ROBO</span> ${esc(event.answer || "")}</p>`}</div></article>`;
  }).join("") : `<div class="empty-history"><div>◷</div><h3>No conversations yet</h3><p>Questions, answers, and scripts Robo speaks will appear here.</p></div>`;
  $("#history-list").innerHTML = content;
  $("#recent-list").innerHTML = events.slice(0,4).map(e => `<div class="recent-item"><span class="recent-icon ${e.kind === "script"?"":"question-icon"}">${e.kind === "script"?"◖":"?"}</span><div><strong>${esc(e.kind === "script"?"Script spoken":e.text)}</strong><small>${esc(e.kind === "script"?e.text:e.answer||"")}</small></div><time>${esc(e.time?new Date(e.time).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"}):"")}</time></div>`).join("") || `<div class="recent-empty">Robo’s recent answers and scripts will show up here.</div>`;
  $("#script-recent-list").innerHTML = events.filter(e=>e.kind==="script").slice(0,3).map(e=>`<div class="recent-item"><span class="recent-icon">◖</span><div><strong>${esc(e.text.slice(0,100))}</strong><small>${esc(e.time?new Date(e.time).toLocaleString():"")}</small></div></div>`).join("") || `<div class="recent-empty">Your recently spoken scripts will show up here.</div>`;
  $("#stat-history").textContent = events.length.toLocaleString();
}
function renderSavedScripts() {
  const select=$("#saved-scripts"), active=state.activeScriptId;
  select.innerHTML=`<option value="">Choose a saved script…</option>`+state.scripts.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
  select.value=state.scripts.some(s=>s.id===active)?active:"";
  $("#delete-script").disabled=!select.value;
}
function abortSpeech() {
  return api("/api/robot/abort-speech",{}).then(()=>toast("Stop requested. Robo will stop speaking now."))
    .catch(error=>toast(error.message,true));
}
function renderRobotStatus(robot={running:false}) {
  const running=Boolean(robot.running||state.browserVoiceActive);
  const activity=robot.running?(robot.activity||{}):{};
  const phase=robot.running?(activity.phase||"STARTING"):(state.browserVoiceActive?(state.browserVoicePhase||"SLEEP"):"STOPPED");
  const labels={STARTING:"STARTING",SLEEP:"GHOST SLEEPING",GREETING:"GREETING",LISTENING:"LISTENING",TRANSCRIPT:"HEARD YOU",THINKING:"THINKING",SPEAKING:"SPEAKING",INTERRUPTING:"STOPPING SPEECH",INTERRUPTED:"SPEECH STOPPED",READY:"READY",STOPPED:"STOPPED"};
  $("#runtime-indicator").classList.toggle("running",running);
  $("#runtime-title").textContent=running?`Robo is ${String(phase).toLowerCase()}`:"Robot conversation is stopped";
  $("#runtime-detail").textContent=running?(activity.detail||`Microphone assistant is running${robot.pid?` · process ${robot.pid}`:""}.`):"Start the microphone assistant to let students talk with Robo.";
  $("#robot-start").classList.toggle("hidden",running);$("#robot-stop").classList.toggle("hidden",!running);
  $("#robot-start").disabled=state.cloudMode && state.settings?.mode !== "offline";
  if(state.cloudMode) $("#robot-start").title=state.settings?.mode === "offline"
    ? "Use browser speech recognition; answers come from the offline SIT knowledge base."
    : "Local microphone and Qwen controls run on your robot computer.";
  $("#robot-run-mode").classList.toggle("hidden",running);
  $("#robot-status-badge").innerHTML=`<i></i> ${running?"ROBOT LISTENING":"CONTROL PANEL READY"}`;
  $("#robot-status-badge").classList.toggle("live",running);
  $("#live-phase").classList.toggle("speaking",phase==="SPEAKING");
  $("#live-phase").innerHTML=`<i></i><span>${esc(labels[phase]||phase)}</span>`;
  $("#live-detail").textContent=state.cloudMode
    ?(state.settings?.mode === "offline"
      ?"Hosted Offline mode: Chrome handles speech recognition; answers come only from the SIT knowledge base."
      :"Cloud demo: text chat and browser speech work here. Local microphone and Qwen controls run on the robot computer.")
    :(activity.detail||(running?"Robo is starting up.":"Start listening to see the current activity here."));
  if(activity.transcript){
    $("#live-transcript").textContent=activity.transcript;
    $("#voice-user-text").textContent=activity.transcript;
  }else if(phase==="LISTENING"){
    $("#live-transcript").textContent="Listening… speak your question after the wake beep.";
    $("#voice-user-text").textContent="Listening… speak your question after the wake beep.";
  }
  if(activity.answer){
    $("#live-answer").textContent=activity.answer;
    $("#voice-bot-text").textContent=activity.answer;
  }else if(phase==="THINKING"||phase==="TRANSCRIPT"){
    $("#voice-bot-text").textContent="I heard you. I’m finding the best answer…";
  }else if(phase==="LISTENING"){
    $("#voice-bot-text").textContent="Robo is listening for your question…";
  }
  $("#live-title").textContent=activity.title||"";
  $("#live-updated").textContent=activity.updated_at?`Updated ${new Date(activity.updated_at).toLocaleTimeString([], {hour:"numeric",minute:"2-digit",second:"2-digit"})}`:"Live state refreshes automatically.";
  $("#abort-speech").classList.toggle("hidden",phase!=="SPEAKING");
  $("#abort-script-speech").classList.toggle("hidden",phase!=="SPEAKING");
  $("#repeat-answer").classList.toggle("hidden",!activity.answer);
  window.dispatchEvent(new CustomEvent("robo-runtime-update", {detail:{running,activity,phase}}));
}
async function refreshRobotStatus(){try{const s=await api("/api/status");renderRobotStatus(s.robot);}catch{}}
async function refreshHistory() { try { state.history = (await api("/api/history")).history; renderHistory(); } catch (_) {} }
async function refreshAll() {
  try {
    const data = await api("/api/bootstrap"); state.knowledge = data.knowledge || []; state.history = data.history || []; state.categories = data.categories || []; state.scripts=data.scripts||[]; state.cloudMode=Boolean(data.cloud_mode); renderSavedScripts();
    const select = $("#category-filter"), previous = select.value;
    select.innerHTML = `<option value="">All categories</option>` + state.categories.map(x=>`<option value="${esc(x)}">${esc(pretty(x))}</option>`).join("");
    if (state.categories.includes(previous)) select.value = previous;
    applySettings(data.settings); renderKnowledge(); renderHistory();
    $("#knowledge-nav-count").textContent = state.knowledge.length;
    refreshRobotStatus();
  } catch (e) { toast(`Could not connect to Robo Brain: ${e.message}`,true); }
}
function slug(text) { return text.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,"").slice(0,60) || "new_answer"; }
function openEditor(item=null) {
  $("#entry-form").reset();
  $("#entry-original-id").value = item?.id || "";
  $("#entry-title").value = item?.title || "";
  $("#entry-id").value = item?.id || "";
  $("#entry-id").readOnly = Boolean(item);
  $("#entry-category").value = item?.category || "general";
  $("#entry-keywords").value = (item?.keywords || []).join("\n");
  $("#entry-answer").value = item?.answer || "";
  $("#modal-title").textContent = item ? "Edit answer" : "Add an answer";
  $("#entry-modal").classList.remove("hidden");
  setTimeout(()=>$("#entry-title").focus(),80);
}
function closeEditor() { $("#entry-modal").classList.add("hidden"); }
async function saveSettings(button) {
  const mode = document.querySelector("input[name=answer-mode]:checked")?.value || "offline";
  const lines = selector => $(selector).value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  const choice = $("#tts-voice").value;
  const [provider, selectedVoiceId] = choice === "system" ? ["system", ""] : choice.includes(":") ? choice.split(":", 2) : ["edge", choice];
  const systemVoice = provider === "system";
  const voiceOption = $("#tts-voice").selectedOptions[0];
  const oldVoice = state.settings?.voice || {};
  const voiceId = systemVoice ? (oldVoice.voice_id || "en-IN-NeerjaNeural") : selectedVoiceId;
  const payload = {
    mode,
    system_prompt: $("#system-prompt").value.trim(),
    voice: {
      provider,
      voice_id: voiceId,
      gender: voiceOption?.dataset.gender || oldVoice.gender || "female",
      name: systemVoice ? "" : voiceId,
      style: $("#tts-style").value,
      speed: Number($("#speed-range").value),
      pitch: Number($("#pitch-range").value),
      volume: Number($("#volume-range").value),
    },
    local_llm: {
      base_url: $("#local-url").value.trim() || "http://127.0.0.1:11434/v1",
      model: $("#local-model").value.trim() || "qwen3:0.6b",
      api_key: $("#local-key").value,
    },
    online: {
      base_url: $("#online-url").value.trim() || "https://generativelanguage.googleapis.com/v1beta/openai",
      model: $("#online-model").value.trim() || "gemini-3.8-flash",
      api_key: $("#online-key").value,
    },
    conversation: {
      welcome: $("#welcome-text").value,
      wake_phrases: lines("#wake-phrases"),
      stop_phrases: lines("#stop-phrases"),
      farewell: $("#farewell-text").value,
      thank_reply: $("#thank-reply").value,
      no_match_reply: $("#no-match-reply").value,
      pause_reply: $("#pause-reply").value,
      listen_timeout: Number($("#listen-timeout").value),
      phrase_time_limit: Number($("#phrase-limit").value),
      sleep_after_answer: Number($("#sleep-after-answer").value),
      mood: $("#robo-mood").value,
      humor_enabled: $("#humor-enabled").checked,
      humor_frequency: Number($("#humor-frequency").value),
    },
    microphone: {
      device_index: Number($("#mic-device").value),
      energy_threshold: Number($("#mic-threshold").value),
      transcription_provider: $("#transcription-provider").value,
    },
  };
  setBusy(button,true,"Saving…");
  try {
    const data = await api("/api/settings", {settings:payload});
    applySettings(data.settings);
    $("#save-status").textContent = "Saved just now · applies to the next answer";
    toast("Robo’s settings are saved.");
    return true;
  } catch (error) {
    toast(error.message,true);
    return false;
  } finally {
    setBusy(button,false);
  }
}

document.querySelectorAll("[data-page]").forEach(b=>b.addEventListener("click",()=>go(b.dataset.page)));
document.querySelectorAll("[data-go]").forEach(b=>b.addEventListener("click",()=>go(b.dataset.go)));
$("#refresh-btn").addEventListener("click",refreshAll);
$("#history-refresh").addEventListener("click",refreshHistory);
$("#knowledge-search").addEventListener("input",renderKnowledge);
$("#category-filter").addEventListener("change",renderKnowledge);
$("#add-entry").addEventListener("click",()=>openEditor());
$("#knowledge-rows").addEventListener("click",async event=>{
  const edit=event.target.closest(".edit-entry"), del=event.target.closest(".delete-entry");
  if(edit){openEditor(state.knowledge.find(x=>x.id===edit.dataset.id));return;}
  if(del){const item=state.knowledge.find(x=>x.id===del.dataset.id);if(!item||!confirm(`Delete “${item.title}” from Robo’s knowledge base?`))return;
    try{const data=await api("/api/knowledge/delete",{id:item.id});state.knowledge=data.knowledge;renderKnowledge();toast("Answer removed from Robo’s knowledge.");}catch(e){toast(e.message,true);}}
});
$("#entry-title").addEventListener("input",()=>{if(!$("#entry-original-id").value)$("#entry-id").value=slug($("#entry-title").value);});
$("#entry-form").addEventListener("submit",async event=>{
  event.preventDefault();const old=state.knowledge.find(x=>x.id===$("#entry-original-id").value);const speakAfterSave=$("#speak-after-save").checked;
  const item={id:$("#entry-id").value.trim(),title:$("#entry-title").value.trim(),category:$("#entry-category").value.trim()||"general",keywords:$("#entry-keywords").value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean),answer:$("#entry-answer").value.trim(),...(old?.sources?{sources:old.sources}:{})};
  const button=$("#entry-form button[type=submit]");setBusy(button,true,"Saving…");
  try{const data=await api("/api/knowledge/save",{item});state.knowledge=data.knowledge;state.categories=[...new Set(state.knowledge.map(x=>x.category||"general"))].sort();renderKnowledge();closeEditor();toast("Saved. Robo can use the updated answer now.");if(speakAfterSave){try{await speakText(item.answer);toast("Saved, and Robo spoke the updated answer.");refreshHistory();}catch(speechError){toast(`Saved, but speech failed: ${speechError.message}`,true);}}}
  catch(e){toast(e.message,true);}finally{setBusy(button,false);}
});
$("#modal-close").addEventListener("click",closeEditor);$("#cancel-entry").addEventListener("click",closeEditor);
$("#entry-modal").addEventListener("click",e=>{if(e.target===$("#entry-modal"))closeEditor();});
$("#speech-text").addEventListener("input",()=>$("#char-count").textContent=`${$("#speech-text").value.length.toLocaleString()} / 12,000`);
$("#saved-scripts").addEventListener("change",()=>{const script=state.scripts.find(s=>s.id===$("#saved-scripts").value);state.activeScriptId=script?.id||"";if(script){$("#script-name").value=script.name;$("#speech-text").value=script.text;$("#char-count").textContent=`${script.text.length.toLocaleString()} / 12,000`;}renderSavedScripts();});
$("#save-script").addEventListener("click",async e=>{const name=$("#script-name").value.trim(),text=$("#speech-text").value.trim();if(!name||!text){toast("Add a script name and text before saving.",true);return;}const btn=e.currentTarget;setBusy(btn,true,"Saving…");try{const data=await api("/api/scripts/save",{id:state.activeScriptId,name,text});state.scripts=data.scripts;state.activeScriptId=data.script.id;renderSavedScripts();toast("Script saved for next time.");}catch(error){toast(error.message,true);}finally{setBusy(btn,false);}});
$("#delete-script").addEventListener("click",async()=>{const id=$("#saved-scripts").value,script=state.scripts.find(s=>s.id===id);if(!script)return;if(!confirm(`Delete saved script “${script.name}”?`))return;try{const data=await api("/api/scripts/delete",{id});state.scripts=data.scripts;state.activeScriptId="";$("#script-name").value="";renderSavedScripts();toast("Saved script deleted.");}catch(error){toast(error.message,true);}});
$("#speak-script").addEventListener("click",async e=>{const btn=e.currentTarget,text=$("#speech-text").value.trim();if(!text){toast("Paste or type the speech first.",true);return;}setBusy(btn,true,"Robo is speaking…");try{await speakText(text);toast("Robo finished speaking.");refreshHistory();}catch(err){toast(err.message,true);}finally{setBusy(btn,false);}});
$("#abort-speech").addEventListener("click",abortSpeech);$("#abort-script-speech").addEventListener("click",abortSpeech);
$("#repeat-answer").addEventListener("click",async e=>{const text=$("#live-answer").textContent.trim();if(!text||text==="Robo’s latest response will appear here.")return;const btn=e.currentTarget;setBusy(btn,true,"Speaking…");try{await speakText(text);toast("Robo repeated the answer.");refreshHistory();}catch(error){toast(error.message,true);}finally{setBusy(btn,false);}});
$("#ask-form").addEventListener("submit",async e=>{e.preventDefault();const query=$("#ask-input").value.trim();if(!query)return;const btn=$("#ask-button");setBusy(btn,true,"Thinking…");$("#ask-result").classList.add("hidden");try{const speak=$("#ask-speak").checked;const data=await api("/api/ask",{query,speak});const r=data.result;$("#ask-result").innerHTML=`<div class="ask-answer-head"><span>ROBO’S ANSWER</span><span>${esc(pretty(r.mode||"offline"))} · ${esc(r.title||"")}</span></div><p>${esc(r.answer)}</p>${r.notice?`<small>${esc(r.notice)}</small>`:""}${r.source?`<a href="${esc(r.source)}" target="_blank" rel="noreferrer">View source ↗</a>`:""}`;$("#ask-result").classList.remove("hidden");state.history.unshift({kind:"conversation",text:query,answer:r.answer,title:r.title,source:"dashboard",time:new Date().toISOString()});renderHistory();$("#ask-input").value="";if(speak&&data.speech_mode==="browser"&&!await speakInBrowser(r.answer))toast("Answer is ready, but this browser has no speech output.",true);}catch(err){toast(err.message,true);}finally{setBusy(btn,false);}});
$("#tts-voice").addEventListener("change",updateRangeLabels);
["#speed-range","#pitch-range","#volume-range"].forEach(q=>$(q).addEventListener("input",updateRangeLabels));
document.querySelectorAll("input[name=answer-mode]").forEach(r=>r.addEventListener("change",toggleOnlineFields));
$("#cloud-provider").addEventListener("change",()=>{if($("#cloud-provider").value==="gemini"){$("#online-url").value="https://generativelanguage.googleapis.com/v1beta/openai";$("#online-model").value="gemini-3.8-flash";}});
// Auto-switch to Cloud AI mode when user starts typing a key in the settings panel
$("#online-key").addEventListener("input", () => {
  if ($("#online-key").value.trim().length >= 10) {
    const onlineRadio = document.querySelector('input[name="answer-mode"][value="online"]');
    if (onlineRadio && !onlineRadio.checked) {
      onlineRadio.checked = true;
      toggleOnlineFields();
      toast("Cloud AI selected. Save settings to apply your key.");
    }
  }
});
$("#save-settings").addEventListener("click",e=>saveSettings(e.currentTarget));$("#save-settings-bottom").addEventListener("click",e=>saveSettings(e.currentTarget));
$("#test-voice").addEventListener("click",async e=>{const btn=e.currentTarget;setBusy(btn,true,"Applying voice…");try{if(!await saveSettings($("#save-settings")))return;setBusy(btn,true,"Speaking…");const result=await speakText("Hello, I am Robo, your campus guide. How can I help you today?");const status=result.voice_status||{};if(result.speech_mode==="browser")toast("Voice sample played in this browser.");else if(status.fallback)toast(`Windows voice used because ${status.voice_id||"the neural voice"} failed: ${status.reason}`,true);else toast(`Voice sample played using ${status.used_voice||status.voice_id||"saved voice settings"}.`);}catch(err){toast(err.message,true);}finally{setBusy(btn,false);}});
$("#test-online").addEventListener("click",async e=>{document.querySelector('input[name="answer-mode"][value="online"]').checked=true;toggleOnlineFields();if(!await saveSettings($("#save-settings")))return;const btn=e.currentTarget;setBusy(btn,true,"Connecting…");try{const result=await api("/api/online/test",{mode:"online"});toast(result.message||"Cloud connection is working.");}catch(err){toast(err.message,true);}finally{setBusy(btn,false);}});
$("#test-local").addEventListener("click",async e=>{document.querySelector('input[name="answer-mode"][value="local"]').checked=true;toggleOnlineFields();if(!await saveSettings($("#save-settings")))return;const btn=e.currentTarget;setBusy(btn,true,"Connecting…");try{const result=await api("/api/online/test",{mode:"local"});toast(result.message||"Local model is working.");}catch(err){toast(err.message,true);}finally{setBusy(btn,false);}});
$("#clear-history").addEventListener("click",async()=>{if(!confirm("Clear all saved conversation and speech history?"))return;try{await api("/api/history/clear",{});state.history=[];renderHistory();toast("History cleared.");}catch(e){toast(e.message,true);}});
$("#robot-start").addEventListener("click",async e=>{const btn=e.currentTarget;setBusy(btn,true,"Starting…");try{window.dispatchEvent(new CustomEvent("robo-browser-voice-start",{detail:{mode:$("#robot-run-mode").value}}));toast("Robo’s browser microphone assistant is starting.");}finally{setBusy(btn,false);}});
$("#robot-stop").addEventListener("click",async e=>{const btn=e.currentTarget;setBusy(btn,true,"Stopping…");try{window.dispatchEvent(new CustomEvent("robo-browser-voice-stop"));toast("Robot conversation stopped.");}finally{setBusy(btn,false);}});

  // Mode badge click toggles between online and offline
  $("#mode-badge").addEventListener("click", async () => {
    const currentMode = state.settings?.mode || "offline";
    const nextMode = currentMode === "online" ? "offline" : "online";
    try {
      const payload = Object.assign({}, state.settings || {}, { mode: nextMode });
      const data = await api("/api/settings", { settings: payload });
      applySettings(data.settings);
      toast(nextMode === "online" ? "✓ Switched to Online (Gemini AI)" : "✓ Switched to Offline SIT Brain");
    } catch (err) {
      toast("Mode switch failed: " + err.message, true);
    }
  });

  // Topbar quick test button
  const quickTestBtn = $("#quick-test-gemini-btn");
  if (quickTestBtn) {
    quickTestBtn.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      setBusy(btn, true, "Testing…");
      try {
        if (state.settings?.mode !== "online") {
          const payload = Object.assign({}, state.settings || {}, { mode: "online" });
          const data = await api("/api/settings", { settings: payload });
          applySettings(data.settings);
        }
        const result = await api("/api/online/test", { mode: "online" });
        toast(result.message || "✓ Gemini online connection is working!");
      } catch (err) {
        toast("Gemini test failed: " + err.message, true);
      } finally {
        setBusy(btn, false);
      }
    });
  }

  // Ask Test Gemini Bot Button in quick chat
  const askTestBtn = $("#ask-test-gemini-btn");
  if (askTestBtn) {
    askTestBtn.addEventListener("click", () => {
      $("#ask-input").value = "Tell me about SIT Tumakuru campus and why it is special.";
      $("#ask-form").dispatchEvent(new Event("submit"));
    });
  }

  // Quick ask chip clicks
  document.querySelectorAll(".quick-chip[data-q]").forEach(chip => {
    chip.addEventListener("click", () => {
      $("#ask-input").value = chip.dataset.q;
      $("#ask-form").dispatchEvent(new Event("submit"));
    });
  });

refreshAll();
let statusInFlight = false;
let statusFailures = 0;
async function guardedRefreshStatus() {
  if (statusInFlight) return;
  statusInFlight = true;
  try {
    const s = await api("/api/status");
    statusFailures = 0;
    renderRobotStatus(s.robot);
  } catch (err) {
    statusFailures++;
  } finally {
    statusInFlight = false;
    // Exponential backoff: 900ms when healthy, up to 10s if backend is unreachable
    const nextDelay = statusFailures === 0 ? 900 : Math.min(10000, 900 * Math.pow(1.5, statusFailures));
    setTimeout(guardedRefreshStatus, nextDelay);
  }
}
setTimeout(guardedRefreshStatus, 900);
$("#connection-retry")?.addEventListener("click", refreshAll);
setInterval(()=>{if(state.backendOnline&&($("#page-history").classList.contains("active")||$("#page-overview").classList.contains("active")))refreshHistory();},12000);


// ============================================================================
// Interactive Human-Robot Voice Assistant with GHOST MODE
// - Dormant SLEEP on startup
// - Local wake-word detection for 'Hey Robo' (0 tokens, 0 cloud calls)
// - 1-second crisp wake beep on detection
// - Microphone activates, Whisper STT -> Gemini -> Neural TTS
// - Auto-returns to SLEEP after answer
// - Self-speech echo suppression (never wakes from its own TTS)
// ============================================================================
(function initVoiceAssistant() {
  const micHero = $("#voice-mic-hero");
  const badge = $("#voice-status-badge");
  const label = $("#voice-status-label");
  const vuFill = $("#voice-vu-fill");
  const vuText = $("#voice-vu-text");
  const userText = $("#voice-user-text");
  const botText = $("#voice-bot-text");
  const wave = $("#voice-speaking-wave");
  const interruptBtn = $("#voice-interrupt-btn");
  const continuousToggle = $("#continuous-voice-toggle");
  const ghostToggle = $("#ghost-mode-toggle");
  const player = $("#voice-player");

  if (!micHero || !player) return;

  let audioCtx = null;
  let micStream = null;
  let analyser = null;
  let mediaRecorder = null;
  let recordedChunks = [];
  let voiceState = "SLEEP"; // "SLEEP" | "LISTENING" | "PROCESSING" | "SPEAKING" | "IDLE"
  let vadActive = false;
  let speechStartTime = 0;
  let lastSpeechTime = 0;
  let isSpeaking = false;
  let ambientFloor = 0.006;
  const silenceTimeoutMs = 1600;
  let wakeRec = null;
  let wakeStopWaiter = null;
  let wakeStopRequested = false;
  let localWakeStartPromise = null;
  let localWakeStarted = false;
  let speechOnsetTime = 0;
  let recordingStartedAt = 0;
  let discardRecording = false;

  // Wake lock and debounce to prevent repeated wake triggers
  let wakeLock = false;
  let lastWakeTime = 0;
  let listenTimeoutTimer = null;

  function playWakeBeep() {
    try {
      const ctx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(1046, ctx.currentTime);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    } catch {
      const audio = new Audio("/api/wake-beep");
      audio.play().catch(() => {});
    }
  }

  function setVoiceUI(voiceStatus, textMsg) {
    voiceState = voiceStatus;
    state.browserVoicePhase = voiceStatus;
    state.browserVoiceActive = voiceStatus !== "IDLE";
    badge.className = `voice-badge ${voiceStatus.toLowerCase()}`;
    const badgeText = voiceStatus === "SLEEP" ? "👻 GHOST SLEEP" :
                      voiceStatus === "LISTENING" ? "👂 LISTENING" :
                      voiceStatus === "PROCESSING" ? "🧠 THINKING" :
                      voiceStatus === "SPEAKING" ? "🗣 SPEAKING" : "⏸ IDLE";
    badge.querySelector("span").textContent = badgeText;
    micHero.className = `voice-mic-hero ${voiceStatus.toLowerCase()}`;
    if (textMsg) label.textContent = textMsg;

    interruptBtn.classList.toggle("hidden", voiceStatus !== "SPEAKING");
    wave.classList.toggle("hidden", voiceStatus !== "SPEAKING");

    if (voiceStatus === "SLEEP") {
      vuFill.style.width = "0%";
      vuText.textContent = "Ghost Mode enabled · Starting browser wake listener…";
    } else if (voiceStatus === "IDLE") {
      vuFill.style.width = "0%";
      vuText.textContent = "Mic ready · Click hero mic to talk";
    }
    if (!localWakeStarted) renderRobotStatus({running:false});
  }

  function startBrowserWakeWord() {
    // Use the browser-owned microphone for every mode so Chrome can request
    // permission. Captured questions are still transcribed by the local
    // Whisper/Vosk engine in Offline and Local Qwen modes.
    if (!state.settings) {
      setTimeout(() => {
        if (ghostToggle.checked && voiceState === "SLEEP") startBrowserWakeWord();
      }, 400);
      return;
    }
    if (state.cloudMode && state.settings.mode === "local") {
      setVoiceUI("IDLE", "Local Qwen is available only on your robot computer");
      vuText.textContent = "Choose Offline SIT answers or Cloud AI for the hosted demo.";
      return;
    }
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      console.error("[WAKE] Browser does not support SpeechRecognition.");
      setVoiceUI("IDLE", "Wake-word detection is unavailable in this browser");
      vuText.textContent = "Use Chrome or Edge, or click the microphone to speak manually.";
      toast("This browser does not support Hey Robo wake detection. Use Chrome/Edge or click the mic.", true);
      return;
    }
    if (wakeRec) {
      try { wakeRec.stop(); } catch {}
    }
    wakeRec = new SpeechRec();
    wakeRec.continuous = true;
    wakeRec.interimResults = true;
    wakeRec.lang = "en-US";

    wakeRec.onstart = () => {
      console.info("[WAKE] Browser wake listener started; waiting for Hey Robo.");
      if (ghostToggle.checked && voiceState === "SLEEP") {
        setVoiceUI("SLEEP", "Waiting for ‘Hey Robo’…");
        const mode = state.settings?.mode;
        vuText.textContent = mode === "offline"
          ? "Browser mic ready · Offline SIT answers · Say ‘Hey Robo’"
          : mode === "local"
            ? "Browser mic ready · Local Qwen answers · Say ‘Hey Robo’"
            : "Wake-word listener active · Say ‘Hey Robo’";
      }
    };

    wakeRec.onresult = (e) => {
      // Ignore if robot is speaking, processing, or already awake
      if (voiceState === "SPEAKING" || voiceState === "PROCESSING" || voiceState === "LISTENING") return;
      if (!ghostToggle.checked) return;

      const now = Date.now();
      if (wakeLock || (now - lastWakeTime < 3000)) return;

      for (let i = e.resultIndex; i < e.results.length; i++) {
        const transcript = e.results[i][0].transcript.toLowerCase();
        // Reliable wake phrase check (debounce prevents multi-firing)
        // Browser recognition may add punctuation ("Hey, Robo") or vary spaces.
        if (/\b(?:hey|hello|hi)[\W_]*(?:robo|robot)\b/.test(transcript)) {
          wakeLock = true;
          lastWakeTime = now;
          console.info("[WAKE] Wake phrase detected:", transcript);
          triggerWakeUp();
          break;
        }
      }
    };

    wakeRec.onerror = (event) => {
      const error = event?.error || "unknown";
      console.error("[WAKE] Browser wake listener error:", error, event);
      if (["not-allowed", "service-not-allowed", "audio-capture"].includes(error)) {
        const message = error === "audio-capture"
          ? "The browser cannot access a microphone. Check Windows and site microphone settings."
          : "Microphone or speech access is blocked. Allow it for 127.0.0.1 in Chrome, then reload.";
        setVoiceUI("IDLE", "Wake-word listener could not start");
        vuText.textContent = message;
        toast(message, true);
        return;
      }
      if (!wakeStopRequested && ghostToggle.checked && voiceState === "SLEEP" && !wakeLock) {
        setTimeout(() => { try { wakeRec?.start(); } catch {} }, 1200);
      }
    };

    wakeRec.onend = () => {
      const stoppedByRequest = wakeStopRequested;
      if (wakeStopWaiter) {
        const resolve = wakeStopWaiter;
        wakeStopWaiter = null;
        resolve();
      }
      if (!stoppedByRequest && ghostToggle.checked && voiceState === "SLEEP" && !wakeLock) {
        setTimeout(() => { try { wakeRec?.start(); } catch {} }, 400);
      }
    };

    try {
      wakeRec.start();
    } catch (error) {
      console.error("[WAKE] Could not start browser wake listener:", error);
      setVoiceUI("IDLE", "Wake-word listener could not start");
      vuText.textContent = "Click the microphone once, allow access, then enable Ghost Mode again.";
      toast("Could not start Hey Robo detection: " + error.message, true);
    }
  }

  function stopBrowserWakeWord() {
    if (!wakeRec) return Promise.resolve();
    const rec = wakeRec;
    wakeStopRequested = true;
    return new Promise(resolve => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        wakeStopRequested = false;
        if (wakeStopWaiter === finish) wakeStopWaiter = null;
        resolve();
      };
      const timer = setTimeout(finish, 900);
      wakeStopWaiter = finish;
      try { rec.stop(); } catch { finish(); }
    });
  }

  async function startLocalWakeWorker() {
    if (state.cloudMode || localWakeStartPromise || localWakeStarted || !ghostToggle.checked) return;
    localWakeStartPromise = (async () => {
      await stopBrowserWakeWord();
      setVoiceUI("SLEEP", "Starting local Hey Robo listener…");
      vuText.textContent = "Starting offline Vosk wake-word detection…";
      try {
        const result = await api("/api/robot/start", {mode: "ghost"});
        renderRobotStatus(result.robot);
        if (!result.robot?.running) throw new Error("The local robot listener did not start.");
        localWakeStarted = true;
        setVoiceUI("SLEEP", "Listening locally for ‘Hey Robo’…");
        vuText.textContent = "Offline Vosk wake listener active · Say ‘Hey Robo’";
        console.info("[WAKE] Offline mode is listening through the local Vosk robot worker.");
      } catch (error) {
        setVoiceUI("IDLE", "Offline wake listener could not start");
        vuText.textContent = error.message;
        toast("Offline wake listener failed: " + error.message, true);
        console.error("[WAKE] Local Vosk listener failed to start:", error);
      }
    })().finally(() => { localWakeStartPromise = null; });
    return localWakeStartPromise;
  }

  async function stopLocalWakeWorker() {
    if (!localWakeStarted) return;
    localWakeStarted = false;
    try {
      const result = await api("/api/robot/stop", {});
      renderRobotStatus(result.robot);
      console.info("[WAKE] Local Vosk listener stopped.");
    } catch (error) {
      toast("Could not stop the local wake listener: " + error.message, true);
    }
  }

  async function triggerWakeUp() {
    // SpeechRecognition owns a browser mic stream. Wait for its onend before
    // opening MediaRecorder's stream, otherwise the first question can be lost.
    await stopBrowserWakeWord();
    playWakeBeep();
    toast("Wake-word detected! Robo is listening.");
    if (state.cloudMode && state.settings?.mode === "offline") {
      startHostedOfflineQuestion();
      return;
    }
    const ready = await setupAudio();
    if (ready) {
      startListening();
    } else {
      enterSleepMode();
    }
  }

  async function startHostedOfflineQuestion() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      toast("This browser cannot transcribe speech. Use Chrome or Edge, or type the question.", true);
      enterSleepMode();
      return;
    }
    setVoiceUI("LISTENING", "Robo is listening · Ask your question");
    vuText.textContent = "Browser speech recognition active · Answers use only the offline SIT knowledge base.";
    let finished = false;
    const finish = async (transcript, error = "") => {
      if (finished) return;
      finished = true;
      clearTimeout(listenTimeoutTimer);
      if (!transcript) {
        if (error) toast("Speech recognition error: " + error, true);
        else toast("I didn’t catch that. Please try again.", true);
        enterSleepMode();
        return;
      }
      await answerHostedOfflineQuestion(transcript);
    };
    const recognition = new SpeechRec();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.lang = "en-IN";
    recognition.onresult = event => {
      const transcript = Array.from(event.results || []).map(result => result[0]?.transcript || "").join(" ").trim();
      finish(transcript);
    };
    recognition.onerror = event => finish("", event.error || "could not recognize speech");
    recognition.onend = () => finish("");
    listenTimeoutTimer = setTimeout(() => {
      try { recognition.stop(); } catch {}
      finish("", "listening timed out");
    }, 20000);
    try {
      // Request microphone permission during this user-initiated wake, then
      // let SpeechRecognition own the mic for the question itself.
      const permissionStream = await navigator.mediaDevices.getUserMedia({audio:true});
      permissionStream.getTracks().forEach(track => track.stop());
      recognition.start();
      console.info("[STT] Hosted Offline mode listening through browser recognition; answer engine remains the local SIT matcher.");
    } catch (error) {
      finish("", error.message || "microphone permission was denied");
    }
  }

  async function answerHostedOfflineQuestion(transcript) {
    setVoiceUI("PROCESSING", "Robo is finding the SIT answer…");
    userText.textContent = transcript;
    $("#live-transcript").textContent = transcript;
    botText.textContent = "Checking the offline SIT knowledge base…";
    $("#live-answer").textContent = "Checking the offline SIT knowledge base…";
    vuText.textContent = "No Gemini or Ollama request · Searching curated SIT answers.";
    try {
      const normalized = transcript.toLowerCase().replace(/[^\w\s]/g, " ").replace(/\s+/g, " ").trim();
      const stopPhrases = state.settings?.conversation?.stop_phrases || ["robo stop", "robot stop", "exit", "quit", "terminate"];
      const stopCommand = stopPhrases.some(phrase => {
        const normalizedPhrase = String(phrase).toLowerCase().replace(/[^\w\s]/g, " ").replace(/\s+/g, " ").trim();
        return normalized === normalizedPhrase || normalized.startsWith(normalizedPhrase + " ");
      });
      const payload = stopCommand ? null : await api("/api/ask", {query:transcript, speak:false});
      const result = payload?.result || {};
      const answer = stopCommand
        ? (state.settings?.conversation?.farewell || "Goodbye! I’ll stop listening now.")
        : (result.answer || "I couldn’t find that in my SIT knowledge base.");
      userText.textContent = transcript;
      botText.textContent = answer;
      $("#live-transcript").textContent = transcript;
      $("#live-answer").textContent = answer;
      $("#live-title").textContent = stopCommand ? "Robo Stopped" : (result.title || "SIT Knowledge Base");
      if (result.notice) vuText.textContent = result.notice;
      state.history.unshift({kind:"conversation", text:transcript, answer, title:result.title || "SIT Knowledge Base", source:"ghost_mode", time:new Date().toISOString()});
      renderHistory();
      console.info("[STT] Browser transcript:", transcript);
      console.info("[OFFLINE] Answered from the SIT knowledge base.");
      setVoiceUI("SPEAKING", "Robo is speaking the offline answer…");
      const spoke = await speakInBrowser(answer);
      if (!spoke) toast("The answer is ready, but browser speech output is unavailable.", true);
      if (stopCommand) {
        ghostToggle.checked = false;
        continuousToggle.checked = false;
        setVoiceUI("IDLE", "Robo stopped · Click Start listening to resume");
      } else if (ghostToggle.checked) enterSleepMode();
      else if (continuousToggle.checked) setTimeout(startHostedOfflineQuestion, 500);
      else setVoiceUI("IDLE", "Answer complete · Click the mic to ask another question");
    } catch (error) {
      botText.textContent = "Error: " + error.message;
      toast("Offline answer failed: " + error.message, true);
      enterSleepMode();
    }
  }

  async function setupAudio() {
    if (audioCtx && micStream) return true;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: { ideal: 16000 },
          channelCount: { ideal: 1 }
        }
      });
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      try { audioCtx = new AudioContextClass({ sampleRate: 16000 }); }
      catch { audioCtx = new AudioContextClass(); }

      const source = audioCtx.createMediaStreamSource(micStream);

      // High-pass filter cuts room/desk rumble below 80 Hz without cutting human speech
      const highpass = audioCtx.createBiquadFilter();
      highpass.type = "highpass";
      highpass.frequency.value = 80;

      // Dynamics Compressor: gently lifts quiet far-field speech while preventing clipping on loud speech
      const compressor = audioCtx.createDynamicsCompressor();
      compressor.threshold.value = -24;
      compressor.knee.value = 12;
      compressor.ratio.value = 4;
      compressor.attack.value = 0.003;
      compressor.release.value = 0.25;

      const gainNode = audioCtx.createGain();
      gainNode.gain.value = 1.2;

      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;

      const dest = audioCtx.createMediaStreamDestination();
      dest.channelCount = 1;
      dest.channelCountMode = "explicit";

      source.connect(highpass);
      highpass.connect(compressor);
      compressor.connect(gainNode);
      gainNode.connect(analyser);
      gainNode.connect(dest);

      // MediaRecorder setup
      const mimeTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/wav"];
      let selectedMime = "";
      for (const mime of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mime)) {
          selectedMime = mime;
          break;
        }
      }

      mediaRecorder = new MediaRecorder(dest.stream, selectedMime ? { mimeType: selectedMime } : {});
      mediaRecorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) recordedChunks.push(e.data);
      };
      mediaRecorder.onstop = handleRecordingComplete;

      startVADLoop();
      console.info(`[RECORD] Mic ready: requested mono 16 kHz, AudioContext ${audioCtx.sampleRate} Hz.`);
      return true;
    } catch (err) {
      if (micStream) micStream.getTracks().forEach(track => track.stop());
      micStream = null;
      if (audioCtx) audioCtx.close().catch(() => {});
      audioCtx = null;
      analyser = null;
      toast("Microphone access denied: " + err.message, true);
      setVoiceUI("IDLE", "Microphone permission needed");
      wakeLock = false;
      return false;
    }
  }

  function startVADLoop() {
    if (vadActive) return;
    vadActive = true;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    function checkAudio() {
      if (!vadActive) return;
      analyser.getByteTimeDomainData(dataArray);

      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const v = (dataArray[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / dataArray.length);

      // Update VU meter UI
      const meterPercent = Math.min(100, Math.round(rms * 400));
      vuFill.style.width = meterPercent + "%";

      // Adapt only while waiting for a phrase. Learning from the user's voice
      // makes the threshold chase speech and can stop long/quiet questions early.
      if (voiceState === "LISTENING" && !isSpeaking) {
        ambientFloor = ambientFloor * 0.98 + rms * 0.02;
      }
      const speechThreshold = Math.max(0.018, ambientFloor * 1.8);
      const silenceThreshold = Math.max(0.010, ambientFloor * 1.25);

      const now = Date.now();

      // 1. Interruption (Barge-in) detection while Robo is speaking
      if (voiceState === "SPEAKING") {
        if (rms > 0.18) {
          interruptSpeech();
          return requestAnimationFrame(checkAudio);
        }
      }

      // 2. Far-field speech detection while LISTENING
      if (voiceState === "LISTENING") {
        if (rms > speechThreshold) {
          if (!isSpeaking) {
            if (!speechOnsetTime) speechOnsetTime = now;
            // Reject isolated clicks without trimming onset audio (recording is
            // already rolling into MediaRecorder's chunks).
            if (now - speechOnsetTime >= 100) {
              isSpeaking = true;
              speechStartTime = speechOnsetTime;
              lastSpeechTime = now;
              label.textContent = "Listening to your question…";
              vuText.textContent = "Speech detected · Speak naturally…";
              clearTimeout(listenTimeoutTimer);
            }
          } else {
            lastSpeechTime = now;
          }
        } else if (!isSpeaking) {
          speechOnsetTime = 0;
        } else {
          if (rms > silenceThreshold) {
            lastSpeechTime = now;
          } else if ((now - lastSpeechTime > silenceTimeoutMs) && (now - speechStartTime > 250)) {
            // Natural pause detected after user spoke -> process question
            isSpeaking = false;
            vuText.textContent = "Question complete · Processing…";
            clearTimeout(listenTimeoutTimer);
            if (mediaRecorder && mediaRecorder.state === "recording") {
              mediaRecorder.stop();
            }
          } else if (now - speechStartTime > Math.min(30000, Math.max(5000,
            Number(state.settings?.conversation?.phrase_time_limit || 15) * 1000))) {
            // Respect the dashboard phrase limit (up to 30 seconds).
            isSpeaking = false;
            clearTimeout(listenTimeoutTimer);
            if (mediaRecorder && mediaRecorder.state === "recording") {
              mediaRecorder.stop();
            }
          }
        }
      }

      requestAnimationFrame(checkAudio);
    }

    requestAnimationFrame(checkAudio);
  }

  function startListening() {
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    isSpeaking = false;
    speechOnsetTime = 0;
    recordedChunks = [];
    setVoiceUI("LISTENING", "Listening… Speak your question now");
    vuText.textContent = "Listening for question (far-field active)…";

    // Start recording immediately so the user's first words are never clipped
    if (mediaRecorder && mediaRecorder.state !== "recording") {
      try {
        mediaRecorder.start(100);
        recordingStartedAt = Date.now();
        console.info("[RECORD] Recording started after wake confirmation.");
      } catch (error) {
        console.error("[ERROR] Could not start microphone recording:", error);
        toast("Could not start recording: " + error.message, true);
        if (ghostToggle.checked) enterSleepMode();
      }
    }

    // Safety timeout: if no speech is detected after 8 seconds, go back to sleep
    clearTimeout(listenTimeoutTimer);
    listenTimeoutTimer = setTimeout(() => {
      if (voiceState === "LISTENING" && !isSpeaking) {
        if (mediaRecorder && mediaRecorder.state === "recording") {
          try { mediaRecorder.stop(); } catch {}
        }
        recordedChunks = [];
        toast("No speech detected. Returning to sleep.");
        enterSleepMode();
      }
    }, 8000);
  }

  function enterSleepMode() {
    clearTimeout(listenTimeoutTimer);
    stopBrowserWakeWord();
    if (voiceState === "LISTENING" && mediaRecorder?.state === "recording") {
      discardRecording = true;
      recordedChunks = [];
      try { mediaRecorder.stop(); } catch {}
    }
    // Release MediaRecorder's mic before the browser wake recognizer reopens it.
    vadActive = false;
    if (micStream) {
      micStream.getTracks().forEach(track => track.stop());
      micStream = null;
    }
    if (audioCtx) {
      const oldContext = audioCtx;
      audioCtx = null;
      analyser = null;
      oldContext.close().catch(() => {});
    }
    wakeLock = false; // Release wake lock
    setVoiceUI("SLEEP", "Ghost Mode: Sleeping silently · Say 'Hey Robo' to wake");
    vuText.textContent = "Ghost Mode enabled · Starting browser wake listener…";
    setTimeout(() => {
      if (ghostToggle.checked && voiceState === "SLEEP") {
        startBrowserWakeWord();
      }
    }, 600);
  }

  async function handleRecordingComplete() {
    clearTimeout(listenTimeoutTimer);
    if (discardRecording) {
      discardRecording = false;
      recordedChunks = [];
      console.info("[RECORD] Discarded because listening was cancelled.");
      return;
    }

    if (!recordedChunks.length) {
      if (ghostToggle.checked) {
        enterSleepMode();
      } else if (continuousToggle.checked) {
        startListening();
      } else {
        setVoiceUI("IDLE", "Click to Start Conversation");
      }
      return;
    }

    const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    recordedChunks = [];

    // Filter tiny clicks / ambient coughs (<1200 bytes)
    const capturedMs = Date.now() - recordingStartedAt;
    console.info(`[RECORD] Recording stopped: ${(capturedMs / 1000).toFixed(2)}s, ${blob.size} bytes, ${blob.type || "unknown audio"}.`);
    if (blob.size < 500 || capturedMs < 300) {
      console.warn("[STT] Empty/invalid transcript: recording too short or empty.");
      if (ghostToggle.checked) {
        enterSleepMode();
      } else if (continuousToggle.checked) {
        startListening();
      } else {
        setVoiceUI("IDLE", "Click to Start Conversation");
      }
      return;
    }

    setVoiceUI("PROCESSING", "Robo is transcribing and thinking…");
    vuText.textContent = "Speech recognition and answer processing…";
    // Clear the last turn while this audio is processed so the UI cannot look
    // as if Robo is replying to the previous question during network latency.
    userText.textContent = "Transcribing the current question…";
    botText.textContent = "Preparing an answer to the current question…";

    try {
      console.info("[STT] Transcription started on the captured question; previous turn cleared.");
      const response = await fetch("/api/ask-voice", {
        method: "POST",
        headers: { "Content-Type": blob.type || "audio/webm" },
        body: blob,
      });

      const data = await response.json();

      if (!data.ok) {
        if (data.reason === "no_speech") {
          vuText.textContent = "No clear speech detected";
          if (ghostToggle.checked) {
            enterSleepMode();
          } else if (continuousToggle.checked) {
            setTimeout(startListening, 600);
          } else {
            setVoiceUI("IDLE", "Click to Start Conversation");
          }
          return;
        }
        throw new Error(data.message || data.error || "Could not process speech");
      }
      if (data.fallback_notice) console.warn("[STT]", data.fallback_notice);

      // Display recognized transcript & response
      userText.textContent = data.transcript || "—";
      botText.textContent = data.answer || "—";
      if (data.transcript) console.info("[STT] Transcript:", data.transcript);
      else console.warn("[STT] Empty/invalid transcript.");

      // Append to live history
      if (data.transcript && data.answer) {
        state.history.unshift({
          kind: "conversation",
          text: data.transcript,
          answer: data.answer,
          title: data.title || "Voice Assistant",
          source: "ghost_mode",
          time: new Date().toISOString()
        });
        renderHistory();
      }

      if (data.is_stop) {
        enterSleepMode();
        playAudio(data.audio_url);
        return;
      }

      // Play synthesized audio response
      setVoiceUI("SPEAKING", "Robo is speaking response…");
      vuText.textContent = "Neural Indian English speech playing";
      await playAudio(data.audio_url);

    } catch (err) {
      toast("Voice error: " + err.message, true);
      botText.textContent = "Error: " + err.message;
      if (ghostToggle.checked) {
        enterSleepMode();
      } else if (continuousToggle.checked) {
        setTimeout(startListening, 1500);
      } else {
        setVoiceUI("IDLE", "Click to Start Conversation");
      }
    }
  }

  function playAudio(url) {
    return new Promise((resolve) => {
      let finished = false;
      let fallbackStarted = false;
      let audioPlaybackStarted = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        console.info("[TTS] Playback completed.");
        onAudioFinished();
        resolve();
      };
      const browserSpeechFallback = () => {
        // Both the media error event and play() rejection can fire for one
        // failed clip. Start fallback speech only once to prevent two voices.
        if (finished || fallbackStarted || audioPlaybackStarted) return;
        fallbackStarted = true;
        try { player.pause(); player.currentTime = 0; } catch {}
        console.info("[TTS] Starting one browser speech fallback.");
        if (window.speechSynthesis && window.SpeechSynthesisUtterance && botText.textContent.trim()) {
          const utterance = new SpeechSynthesisUtterance(botText.textContent.trim());
          const savedVoice = state.settings?.voice || {};
          utterance.lang = "en-IN";
          utterance.rate = Math.max(.65, Math.min(1.4, Number(savedVoice.speed) || 1));
          utterance.pitch = Math.max(.5, Math.min(2, 1 + (Number(savedVoice.pitch) || 0) / 10));
          utterance.volume = Math.max(0, Math.min(1, (Number(savedVoice.volume) || 100) / 100));
          const voices = window.speechSynthesis.getVoices();
          const gender = String(savedVoice.gender || "").toLowerCase();
          utterance.voice = voices.find(voice => /^en[-_]in$/i.test(voice.lang) && (!gender || voice.name.toLowerCase().includes(gender)))
            || voices.find(voice => /^en[-_]in$/i.test(voice.lang))
            || null;
          utterance.onend = finish;
          utterance.onerror = finish;
          try { window.speechSynthesis.speak(utterance); }
          catch { finish(); }
          return;
        }
        finish();
      };
      if (!url) {
        return browserSpeechFallback();
      }
      fetch(url, {cache:"no-store"}).then(async response => {
        if (!response.ok) throw new Error("Neural voice audio is unavailable.");
        const audioUrl = URL.createObjectURL(await response.blob());
        const releaseAudio = () => URL.revokeObjectURL(audioUrl);
        player.src = audioUrl;
        const configuredVolume = Number(state.settings?.voice?.volume);
        player.volume = Math.max(0, Math.min(1, Number.isFinite(configuredVolume) ? configuredVolume / 100 : 1));
        player.onplaying = () => { audioPlaybackStarted = true; };
        player.onended = () => { releaseAudio(); finish(); };
        player.onerror = () => {
          releaseAudio();
          if (audioPlaybackStarted) finish();
          else browserSpeechFallback();
        };
        try { await player.play(); }
        catch (_) {
          releaseAudio();
          if (audioPlaybackStarted) finish();
          else browserSpeechFallback();
        }
      }).catch(browserSpeechFallback);
    });
  }

  function onAudioFinished() {
    if (ghostToggle.checked) {
      enterSleepMode();
    } else if (continuousToggle.checked) {
      setTimeout(startListening, 600);
    } else {
      setVoiceUI("IDLE", "Click to Start Conversation");
    }
  }

  function interruptSpeech() {
    try {
      player.pause();
      player.currentTime = 0;
    } catch {}
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    abortSpeech();
    toast("Speech interrupted by user.");
    if (ghostToggle.checked) {
      enterSleepMode();
    } else if (continuousToggle.checked) {
      setTimeout(startListening, 300);
    } else {
      setVoiceUI("IDLE", "Speech stopped · Click to start");
    }
  }

  // Event Listeners
  micHero.addEventListener("click", async () => {
    if (state.settings?.mode !== "online" && ghostToggle.checked && voiceState === "SLEEP") {
      // A click is the reliable user gesture for the browser permission prompt
      // and is also a manual wake fallback if browser wake recognition is unavailable.
      wakeLock = true;
      lastWakeTime = Date.now();
      await triggerWakeUp();
      return;
    }
    if (voiceState === "SPEAKING") {
      interruptSpeech();
      return;
    }
    if (voiceState === "LISTENING") {
      if (ghostToggle.checked) {
        enterSleepMode();
      } else {
        clearTimeout(listenTimeoutTimer);
        if (mediaRecorder?.state === "recording") {
          discardRecording = true;
          recordedChunks = [];
          try { mediaRecorder.stop(); } catch {}
        }
        isSpeaking = false;
        setVoiceUI("IDLE", "Conversation paused");
      }
      return;
    }
    // Manual wake-up fallback from SLEEP or IDLE
    triggerWakeUp();
  });

  interruptBtn.addEventListener("click", interruptSpeech);

  window.addEventListener("robo-settings-applied", async (event) => {
    if (!ghostToggle.checked) return;
    if (state.cloudMode) {
      await stopLocalWakeWorker();
      if (["online", "offline"].includes(event.detail?.mode)) {
        startBrowserWakeWord();
      } else {
        await stopBrowserWakeWord();
        wakeLock = false;
        setVoiceUI("IDLE", "Local Qwen requires the robot computer");
        vuText.textContent = "Choose Offline SIT answers or Cloud AI for the hosted demo.";
      }
      return;
    }
    await stopLocalWakeWorker();
    if (voiceState === "SLEEP") startBrowserWakeWord();
  });

  window.addEventListener("robo-runtime-update", (event) => {
    // Runtime events describe the separate Python microphone worker. It is no
    // longer used by the dashboard voice flow, which owns its mic in Chrome.
    if (state.settings?.mode === "online" || !localWakeStarted) return;
    const {running, activity = {}, phase = "STOPPED"} = event.detail || {};
    if (!running) {
      setVoiceUI("IDLE", "Offline robot stopped · Start listening on Overview");
      vuText.textContent = "Local Vosk wake listener is stopped.";
      return;
    }
    if (phase === "SLEEP") {
      setVoiceUI("SLEEP", "Waiting for ‘Hey Robo’…");
      vuText.textContent = "Offline Vosk wake listener active · Say ‘Hey Robo’";
    } else if (phase === "LISTENING") {
      setVoiceUI("LISTENING", "Robo heard you · Ask your question now");
      vuText.textContent = "Recording your question from the local microphone…";
    } else if (phase === "TRANSCRIPT" || phase === "THINKING") {
      setVoiceUI("PROCESSING", "Robo is understanding your question…");
      vuText.textContent = activity.transcript ? `Heard: ${activity.transcript}` : "Searching the offline SIT knowledge base…";
    } else if (phase === "SPEAKING") {
      setVoiceUI("SPEAKING", "Robo is speaking the answer…");
      vuText.textContent = activity.answer || "Speaking the offline answer…";
    } else if (phase === "READY") {
      setVoiceUI("SLEEP", "Waiting for ‘Hey Robo’…");
      vuText.textContent = "Offline Vosk wake listener active · Say ‘Hey Robo’";
    }
  });

  window.addEventListener("robo-robot-stopped", () => { localWakeStarted = false; });

  window.addEventListener("robo-browser-voice-start", async (event) => {
    if (state.cloudMode && state.settings?.mode !== "offline") {
      toast("Local microphone and Qwen control are available on the robot computer.", true);
      return;
    }
    const mode = event.detail?.mode || "ghost";
    try {
      if (mode === "ghost") {
        // Request permission from a direct button click, then release this
        // temporary stream before the wake listener takes over the microphone.
        const permissionStream = await navigator.mediaDevices.getUserMedia({audio: true});
        permissionStream.getTracks().forEach(track => track.stop());
        // Shut down a Vosk/Python listener left over from an earlier session;
        // otherwise it can contend with Chrome for the same microphone.
        localWakeStarted = false;
        try { await api("/api/robot/stop", {}); } catch {}
        ghostToggle.checked = true;
        enterSleepMode();
      } else {
        const permissionStream = await navigator.mediaDevices.getUserMedia({audio: true});
        permissionStream.getTracks().forEach(track => track.stop());
        ghostToggle.checked = false;
        await stopBrowserWakeWord();
        if (state.cloudMode && state.settings?.mode === "offline") {
          startHostedOfflineQuestion();
        } else {
          const ready = await setupAudio();
          if (ready) startListening();
        }
      }
      renderRobotStatus({running:false});
    } catch (error) {
      setVoiceUI("IDLE", "Microphone permission is needed to start Robo");
      vuText.textContent = "Allow microphone access for this site in Chrome, then press Start listening again.";
      toast("Could not access the microphone: " + error.message, true);
    }
  });

  window.addEventListener("robo-browser-voice-stop", async () => {
    ghostToggle.checked = false;
    continuousToggle.checked = false;
    wakeLock = false;
    clearTimeout(listenTimeoutTimer);
    await stopBrowserWakeWord();
    await stopLocalWakeWorker();
    try { await api("/api/robot/stop", {}); } catch {}
    if (mediaRecorder?.state === "recording") {
      discardRecording = true;
      recordedChunks = [];
      try { mediaRecorder.stop(); } catch {}
    }
    if (micStream) {
      micStream.getTracks().forEach(track => track.stop());
      micStream = null;
    }
    if (audioCtx) {
      const oldContext = audioCtx;
      audioCtx = null;
      analyser = null;
      oldContext.close().catch(() => {});
    }
    setVoiceUI("IDLE", "Conversation stopped · Click Start listening to resume");
    renderRobotStatus({running:false});
  });

  ghostToggle.addEventListener("change", () => {
    if (ghostToggle.checked) {
      toast("Ghost Mode active: Robo is sleeping. Say 'Hey Robo' to wake.");
      enterSleepMode();
    } else {
      stopBrowserWakeWord();
      stopLocalWakeWorker();
      wakeLock = false;
      setVoiceUI("IDLE", "Ghost Mode disabled · Click to start");
    }
  });

  // On startup: Enter SLEEP mode when Ghost Mode is checked
  if (ghostToggle.checked) {
    enterSleepMode();
  }

})();
