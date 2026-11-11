import { useRef, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

function formatBytes(bytes = 0) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function App() {
  const [activeTab, setActiveTab] = useState("Overview");
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [processedData, setProcessedData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [question, setQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [isAsking, setIsAsking] = useState(false);
  const [libraryVideos, setLibraryVideos] = useState([]);
  const [isLoadingLibrary, setIsLoadingLibrary] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [isImportingYoutube, setIsImportingYoutube] = useState(false);

  const fileInputRef = useRef(null);
  const videoPlayerRef = useRef(null);
  const chatEndRef = useRef(null);
  const summaryRef = useRef(null);
  const transcriptRef = useRef(null);
  const chatRef = useRef(null);

  const transcript = processedData?.transcript || "";
  const videoUrl = processedData?.video_url
    ? `${API_BASE}${processedData.video_url}`
    : "";

  const refreshLibrary = async () => {
    setIsLoadingLibrary(true);
    try {
      const response = await fetch(`${API_BASE}/videos`);
      const result = await response.json();
      if (!response.ok) throw new Error(result?.detail || "Could not load video library.");
      setLibraryVideos(Array.isArray(result.videos) ? result.videos : []);
    } catch (error) {
      setUploadMessage(`Library error: ${error.message}`);
    } finally {
      setIsLoadingLibrary(false);
    }
  };

  const openSavedVideo = async (sourceId) => {
    try {
      const response = await fetch(`${API_BASE}/videos/${encodeURIComponent(sourceId)}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result?.detail || "Could not open saved video.");
      setProcessedData({
        transcript: result.transcript,
        transcript_file: result.transcript_file,
        video_file: result.video_file,
        video_url: result.video_url,
        indexed_chunks: 0,
      });
      setSelectedFile({ name: result.title || sourceId, size: 0 });
      setSummary(null);
      setChatMessages([]);
      setShowTranscript(false);
      setActiveTab("Overview");
      setUploadMessage("Saved analysis loaded. You can view its transcript and ask questions.");
    } catch (error) {
      setUploadMessage(`Could not open saved analysis: ${error.message}`);
    }
  };

  const handleYouTubeImport = async (event) => {
    event?.preventDefault();
    if (!youtubeUrl.trim() || isImportingYoutube) return;
    setIsImportingYoutube(true);
    setUploadMessage("Importing YouTube video and processing its audio. This may take a while...");
    setProcessedData(null);
    setSummary(null);
    setChatMessages([]);
    try {
      const response = await fetch(`${API_BASE}/youtube`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: youtubeUrl.trim() }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result?.detail || "YouTube import failed.");
      setProcessedData(result);
      setSelectedFile({ name: result.title || result.video_file || "YouTube video", size: 0 });
      setYoutubeUrl("");
      setUploadMessage("YouTube video imported and processed successfully.");
      setActiveTab("Overview");
      await refreshLibrary();
    } catch (error) {
      setUploadMessage(`YouTube import error: ${error.message}`);
    } finally {
      setIsImportingYoutube(false);
    }
  };

  const scrollTo = (ref) => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleFile = (file) => {
    if (!file) return;
    setSelectedFile(file);
    setUploadMessage("");
    setProcessedData(null);
    setSummary(null);
    setChatMessages([]);
    setShowTranscript(false);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setUploadMessage("Choose a video or audio file to get started.");
      return;
    }

    setIsUploading(true);
    setUploadMessage("Uploading your media and preparing its transcript...");
    setProcessedData(null);
    setSummary(null);
    setChatMessages([]);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const response = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
      });
      const responseText = await response.text();
      let result;
      try {
        result = JSON.parse(responseText);
      } catch {
        result = { detail: responseText };
      }
      if (!response.ok) {
        throw new Error(result?.detail || "Upload failed. Please try again.");
      }
      setProcessedData(result);
      setUploadMessage("Your media is ready. You can now explore its summary and ask questions.");
      setActiveTab("Overview");
      await refreshLibrary();
    } catch (error) {
      setUploadMessage(`Could not process this file: ${error.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleGenerateSummary = async () => {
    if (!transcript) {
      setUploadMessage("The transcript is not available for this file.");
      return;
    }
    setIsSummarizing(true);
    setUploadMessage("");
    try {
      const response = await fetch(`${API_BASE}/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.detail || "Summary generation failed.");
      }
      setSummary(result);
      setTimeout(() => scrollTo(summaryRef), 80);
    } catch (error) {
      setUploadMessage(`Summary error: ${error.message}`);
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleAskQuestion = async (event) => {
    event?.preventDefault();
    const cleanQuestion = question.trim();
    if (!cleanQuestion || isAsking) return;

    if (!processedData?.transcript_file) {
      setChatMessages((previous) => [
        ...previous,
        { role: "assistant", answer: "Please upload and process a video first.", sources: [] },
      ]);
      return;
    }

    setChatMessages((previous) => [...previous, { role: "user", question: cleanQuestion }]);
    setQuestion("");
    setIsAsking(true);

    try {
      // Keep the exact transcript filename returned by the backend, including .txt.
      const response = await fetch(`${API_BASE}/ask-video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: processedData.transcript_file,
          question: cleanQuestion,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.detail || "Unable to get an answer.");
      }
      setChatMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          answer: typeof result.answer === "string"
            ? result.answer
            : JSON.stringify(result.answer, null, 2),
          sources: Array.isArray(result.sources) ? result.sources : [],
        },
      ]);
    } catch (error) {
      setChatMessages((previous) => [
        ...previous,
        { role: "assistant", answer: `I couldn't complete that request: ${error.message}`, sources: [] },
      ]);
    } finally {
      setIsAsking(false);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  };

  const jumpToTimestamp = (seconds) => {
    if (!videoPlayerRef.current || typeof seconds !== "number") return;
    videoPlayerRef.current.currentTime = seconds;
    videoPlayerRef.current.play().catch(() => {});
  };

  const renderSummary = () => {
    if (!summary) return null;
    const summaryText = typeof summary === "string"
      ? summary
      : summary.summary || summary.overview || summary.text || "";
    const keyPoints = summary.key_points || summary.keyPoints || summary.highlights || [];
    const actionItems = summary.action_items || summary.actionItems || [];

    return (
      <div className="result-card summary-result">
        <div className="result-card-heading">
          <div>
            <span className="eyebrow">YOUR VIDEO, SIMPLIFIED</span>
            <h3>Here's the big picture</h3>
            <p>A readable overview of the most important information.</p>
          </div>
          <span className="result-icon">✦</span>
        </div>
        {summaryText ? <p className="summary-copy">{summaryText}</p> : null}
        {Array.isArray(keyPoints) && keyPoints.length > 0 && (
          <div className="summary-subsection">
            <h4><span className="mini-dot purple-dot" /> Key takeaways</h4>
            <ul className="insight-list">
              {keyPoints.map((point, index) => (
                <li key={index}>{typeof point === "string" ? point : point.text || point.title || JSON.stringify(point)}</li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(actionItems) && actionItems.length > 0 && (
          <div className="summary-subsection">
            <h4><span className="mini-dot green-dot" /> Action items</h4>
            <ul className="insight-list action-list">
              {actionItems.map((item, index) => (
                <li key={index}>{typeof item === "string" ? item : item.text || item.task || item.title || JSON.stringify(item)}</li>
              ))}
            </ul>
          </div>
        )}
        {!summaryText && !keyPoints.length && !actionItems.length && (
          <pre className="summary-copy">{JSON.stringify(summary, null, 2)}</pre>
        )}
      </div>
    );
  };

  const renderChat = () => (
    <section className="workspace-card chat-card" ref={chatRef} id="assistant">
      <div className="section-heading">
        <div>
          <span className="eyebrow">YOUR VIDEO, YOUR QUESTIONS</span>
          <h2>Chat with your video</h2>
          <p>Ask naturally. VYBE AI answers using the content of your uploaded media.</p>
        </div>
        <div className="assistant-status"><span /> AI ready</div>
      </div>

      <div className="chat-window">
        {chatMessages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">✳</div>
            <h3>Let's explore your video.</h3>
            <p>Ask about key moments, people, decisions, timelines or anything discussed.</p>
            <div className="suggested-questions">
              {[
                "Give me the main points of this video",
                "What decisions were made?",
                "What are the important deadlines?",
              ].map((item) => (
                <button key={item} type="button" onClick={() => setQuestion(item)}>{item}<span>↗</span></button>
              ))}
            </div>
          </div>
        ) : (
          <div className="message-list">
            {chatMessages.map((message, index) => (
              <div className={`message-row ${message.role}`} key={index}>
                {message.role === "assistant" && <div className="message-avatar">✳</div>}
                <div className="message-content">
                  <span className="message-author">{message.role === "user" ? "You" : "VYBE AI"}</span>
                  <div className="message-bubble">
                    <p>{message.role === "user" ? message.question : message.answer}</p>
                    {message.role === "assistant" && message.sources?.length > 0 && (
                      <div className="source-block">
                        <div className="source-heading">REFERENCES FROM YOUR VIDEO</div>
                        {message.sources.map((source, sourceIndex) => (
                          <div className="source-item" key={`${source.start ?? sourceIndex}-${source.end ?? ""}-${sourceIndex}`}>
                            <button
                              type="button"
                              className="timestamp-button"
                              onClick={() => jumpToTimestamp(source.start)}
                              disabled={!videoUrl || typeof source.start !== "number"}
                              title={videoUrl ? "Jump to this moment" : "Video playback is not available for this audio file"}
                            >
                              <span>▶</span> {source.start_timestamp || "Source"}{source.end_timestamp ? ` – ${source.end_timestamp}` : ""}
                            </button>
                            <p>{source.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {isAsking && (
              <div className="message-row assistant">
                <div className="message-avatar">✳</div>
                <div className="message-content">
                  <span className="message-author">VYBE AI</span>
                  <div className="message-bubble typing"><span /><span /><span /></div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}
      </div>

      <form className="chat-composer" onSubmit={handleAskQuestion}>
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={processedData ? "Ask a follow-up question..." : "Upload a video to start chatting..."}
          disabled={!processedData || isAsking}
        />
        <button type="submit" disabled={!processedData || !question.trim() || isAsking} aria-label="Send question">
          {isAsking ? "..." : "Send"} <span>➤</span>
        </button>
      </form>
      <div className="chat-footnote">Answers are grounded in the processed transcript. Source references appear when relevant passages are found.</div>
    </section>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setActiveTab("Overview")} type="button">
          <div className="brand-icon">V</div>
          <div><h2>VYBE<span>AI</span></h2><p>VIDEO INTELLIGENCE</p></div>
        </button>

        <div className="nav-label">WORKSPACE</div>
        <nav className="navigation">
          {[
            { name: "Overview", icon: "◫" },
            { name: "My Videos", icon: "▣" },
            { name: "AI Assistant", icon: "✳" },
          ].map((item) => (
            <button
              key={item.name}
              className={`nav-item ${activeTab === item.name ? "active" : ""}`}
              onClick={() => {
                setActiveTab(item.name);
                if (item.name === "AI Assistant") setTimeout(() => scrollTo(chatRef), 80);
                if (item.name === "My Videos") refreshLibrary();
              }}
              type="button"
            >
              <span className="nav-icon">{item.icon}</span>{item.name}
              {item.name === "AI Assistant" && <span className="new-badge">AI</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="upgrade-card">
            <div className="upgrade-icon">✦</div>
            <h3>Make every video useful</h3>
            <p>Turn long recordings into clear answers, summaries and next steps.</p>
          </div>
          <div className="profile">
            <div className="avatar">V</div>
            <div><h4>My Workspace</h4><p>Personal workspace</p></div>
            <span className="profile-menu">•••</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> {activeTab}</div>
          <div className="topbar-right"><span className="status-indicator"><span /> LOCAL API</span></div>
        </header>

        {activeTab === "My Videos" ? (
          <div className="page-content">
            <section className="page-title">
              <span className="eyebrow">YOUR LIBRARY</span>
              <h1>My <span>Videos</span></h1>
              <p>Your previously processed videos and audio recordings, saved on this device.</p>
            </section>
            <div className="section-heading">
              <div><h2>Saved analyses</h2><p>Open any item to continue reading, reviewing or chatting.</p></div>
              <button className="secondary-button" type="button" onClick={refreshLibrary} disabled={isLoadingLibrary}>{isLoadingLibrary ? "Refreshing..." : "↻ Refresh"}</button>
            </div>
            {isLoadingLibrary && <div className="placeholder-card"><p>Loading your library...</p></div>}
            {!isLoadingLibrary && libraryVideos.length > 0 && (
              <div className="library-list">
                {libraryVideos.map((item) => (
                  <div className="library-item" key={item.source_id}>
                    <div className="library-thumb">▶</div>
                    <div className="library-info">
                      <h3>{item.title || item.source_id}</h3>
                      <p>{item.has_video ? "Video available" : "Transcript available"} · {item.source_id}</p>
                      <span className="library-status">✓ Saved analysis</span>
                    </div>
                    <button className="secondary-button" onClick={() => openSavedVideo(item.source_id)} type="button">Open analysis →</button>
                  </div>
                ))}
              </div>
            )}
            {!isLoadingLibrary && libraryVideos.length === 0 && (
              <div className="empty-library">
                <div className="empty-icon">▣</div>
                <h2>No saved analyses yet</h2>
                <p>Upload a video or import a YouTube link to create your first analysis.</p>
                <button className="primary-button" onClick={() => setActiveTab("Overview")} type="button">Add media →</button>
              </div>
            )}
            <p className="library-note">The library is built from saved transcript files in your backend project. Keep the project data folder to retain your history.</p>
          </div>
        ) : (
          <div className="page-content">
            {activeTab === "Overview" && (
              <>
                <section className="welcome-section">
                  <div className="welcome-content">
                    <span className="eyebrow"><span className="eyebrow-sparkle">✦</span> YOUR PERSONAL VIDEO WORKSPACE</span>
                    <h1>Turn videos into <span>insights.</span></h1>
                    <p>Understand more in less time. Upload a recording, get a clear summary, explore the transcript and ask questions in a natural conversation.</p>
                  </div>
                  <div className="welcome-decoration">✳</div>
                </section>

                <section className="upload-section">
                  <div className="section-heading">
                    <div><h2>Start a new analysis</h2><p>Bring a video or audio recording into your workspace.</p></div>
                    <span className="supported-label">AUDIO & VIDEO</span>
                  </div>
                  <div
                    className="upload-card"
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => { event.preventDefault(); handleFile(event.dataTransfer.files?.[0]); }}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="audio/*,video/*"
                      hidden
                      onChange={(event) => handleFile(event.target.files?.[0])}
                    />
                    <div className="upload-icon"><span>↑</span></div>
                    <h3>{selectedFile ? "Your file is ready" : "Drop your media here"}</h3>
                    <p>{selectedFile ? "Ready when you are. Start the analysis to transcribe and index your media." : "Drag and drop a file, or browse your device. Your media will be transcribed and prepared for AI questions."}</p>
                    {selectedFile && <div className="selected-file"><span>▣</span><strong>{selectedFile.name}</strong><small>{formatBytes(selectedFile.size)}</small></div>}
                    <div className="upload-actions">
                      <button className="secondary-button" type="button" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>Choose a file</button>
                      {selectedFile && <button className="primary-button" type="button" onClick={handleUpload} disabled={isUploading}>{isUploading ? "Processing..." : "Analyze media →"}</button>}
                    </div>
                    <div className="format-label">SUPPORTED: MP4 · MOV · MP3 · WAV · M4A · AND MORE</div>
                    {isUploading && <div className="progress-track"><span /></div>}
                    {uploadMessage && <p className={`upload-message ${uploadMessage.startsWith("Could not") || uploadMessage.startsWith("Summary error") ? "error" : ""}`}>{uploadMessage}</p>}
                    {processedData && <div className="success-line">✓ Processing complete <span>·</span> {processedData.indexed_chunks ?? 0} chunks indexed</div>}
                  </div>
                </section>

                <section className="upload-section youtube-import-section">
                  <div className="section-heading">
                    <div><h2>Import from YouTube</h2><p>Paste a public YouTube video link to transcribe and analyze it.</p></div>
                    <span className="supported-label">YOUTUBE</span>
                  </div>
                  <form className="chat-composer" onSubmit={handleYouTubeImport}>
                    <input
                      type="url"
                      value={youtubeUrl}
                      onChange={(event) => setYoutubeUrl(event.target.value)}
                      placeholder="https://www.youtube.com/watch?v=..."
                      disabled={isImportingYoutube}
                    />
                    <button type="submit" disabled={!youtubeUrl.trim() || isImportingYoutube}>
                      {isImportingYoutube ? "Importing..." : "Import video →"}
                    </button>
                  </form>
                  <p className="chat-footnote">Public videos only. Import availability depends on YouTube access and the video's permissions. Very long videos may take time and use local storage.</p>
                </section>

                {processedData && (
                  <section className="analysis-section">
                    <div className="section-heading">
                      <div><span className="eyebrow">ANALYSIS WORKSPACE</span><h2>{selectedFile?.name || "Your uploaded media"}</h2><p>Your recording is processed. Choose an insight or start a conversation.</p></div>
                      <span className="ready-pill"><span /> READY</span>
                    </div>

                    {videoUrl && (
                      <div className="video-panel">
                        <div className="video-panel-heading"><div><h3>Media preview</h3><p>Use source timestamps in the chat to jump to a moment.</p></div><span>▶ VIDEO</span></div>
                        <video ref={videoPlayerRef} controls preload="metadata" src={videoUrl}>Your browser does not support video playback.</video>
                      </div>
                    )}

                    <div className="quick-actions">
                      <button type="button" className="quick-action" onClick={() => { scrollTo(summaryRef); if (!summary && !isSummarizing) handleGenerateSummary(); }}>
                        <span className="quick-icon purple-icon">✦</span><span><strong>Smart summary</strong><small>Understand the main ideas</small></span><b>↗</b>
                      </button>
                      <button type="button" className="quick-action" onClick={() => { setShowTranscript(true); setTimeout(() => scrollTo(transcriptRef), 80); }}>
                        <span className="quick-icon blue-icon">▤</span><span><strong>Full transcript</strong><small>Read everything that was said</small></span><b>↗</b>
                      </button>
                      <button type="button" className="quick-action" onClick={() => { setActiveTab("AI Assistant"); setTimeout(() => scrollTo(chatRef), 80); }}>
                        <span className="quick-icon pink-icon">✳</span><span><strong>Ask the AI</strong><small>Explore your video in chat</small></span><b>↗</b>
                      </button>
                      <button type="button" className="quick-action" onClick={() => {
                        const firstSource = chatMessages.flatMap((message) => message.sources || [])[0];
                        if (firstSource) jumpToTimestamp(firstSource.start);
                        else if (videoUrl) videoPlayerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
                        else scrollTo(chatRef);
                      }}>
                        <span className="quick-icon green-icon">◷</span><span><strong>Key moments</strong><small>Jump to cited video moments</small></span><b>↗</b>
                      </button>
                    </div>

                    <div ref={summaryRef} className="content-anchor">
                      <div className="section-heading result-section-heading">
                        <div><h2>Smart summary</h2><p>A structured view of what matters in this recording.</p></div>
                        <button className="secondary-button" type="button" onClick={handleGenerateSummary} disabled={isSummarizing}>{isSummarizing ? "Generating..." : summary ? "Regenerate summary" : "Generate summary ✦"}</button>
                      </div>
                      {summary ? renderSummary() : (
                        <div className="placeholder-card"><div className="placeholder-icon">✦</div><div><h3>Your summary will appear here</h3><p>Generate a summary to get the overview, key takeaways and action items from this recording.</p></div></div>
                      )}
                    </div>

                    <div className="content-anchor" ref={transcriptRef}>
                      <div className="section-heading result-section-heading">
                        <div><h2>Transcript</h2><p>The original words captured from your recording.</p></div>
                        <button className="secondary-button" type="button" onClick={() => setShowTranscript((value) => !value)}>{showTranscript ? "Collapse transcript ↑" : "Read transcript ↓"}</button>
                      </div>
                      {showTranscript && (
                        <div className="transcript-card">
                          <div className="transcript-toolbar"><span>ORIGINAL TRANSCRIPT</span><span>{transcript.split(/\s+/).filter(Boolean).length.toLocaleString()} words</span></div>
                          <p>{transcript || "Transcript not available."}</p>
                        </div>
                      )}
                    </div>

                    {renderChat()}
                  </section>
                )}

                {!processedData && (
                  <section className="features-section">
                    <div className="section-heading"><div><h2>One recording. Many possibilities.</h2><p>Everything you can do once your media is processed.</p></div></div>
                    <div className="feature-grid">
                      <div className="feature-card purple"><div className="feature-icon">✦</div><h3>Smart summaries</h3><p>Get the overview, key takeaways and action items without replaying the entire recording.</p></div>
                      <div className="feature-card blue"><div className="feature-icon">✳</div><h3>AI video chat</h3><p>Ask follow-up questions in natural language and get answers grounded in the transcript.</p></div>
                      <div className="feature-card pink"><div className="feature-icon">◷</div><h3>Source moments</h3><p>See the transcript passages that support an answer and jump to the relevant video moment.</p></div>
                      <div className="feature-card green"><div className="feature-icon">☷</div><h3>Actionable insights</h3><p>Bring important discussion points and next steps into focus.</p></div>
                    </div>
                  </section>
                )}
              </>
            )}

            {activeTab === "AI Assistant" && (
              <>
                <section className="page-title"><span className="eyebrow">VIDEO GROUNDED CONVERSATION</span><h1>AI <span>Assistant</span></h1><p>Ask questions and explore the content of your currently processed recording.</p></section>
                {processedData ? renderChat() : (
                  <div className="empty-library"><div className="empty-icon">✳</div><h2>Upload a recording to begin</h2><p>Your assistant needs a processed transcript to answer questions about a video.</p><button className="primary-button" onClick={() => setActiveTab("Overview")} type="button">Go to upload →</button></div>
                )}
              </>
            )}
          </div>
        )}

        <footer className="footer"><span>VYBE AI © 2026</span><span>BUILT FOR BETTER UNDERSTANDING <span className="footer-star">✦</span></span></footer>
      </main>
    </div>
  );
}

export default App;
