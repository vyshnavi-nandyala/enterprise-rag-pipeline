import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import {
  AlertCircle,
  Bot,
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  FileText,
  Loader2,
  Send,
  Shield,
  Upload,
  User,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface SourceCitation {
  source_id: number;
  filename: string;
  department: string | null;
  chunk_index: number;
  excerpt: string;
  similarity_score: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  retrieval_latency_ms?: number;
  total_latency_ms?: number;
  token_cost_usd?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  flagged_for_injection?: boolean;
  pii_detected?: boolean;
  timestamp: Date;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const API_KEY = import.meta.env.VITE_API_KEY ?? "changeme-api-key";

const SUGGESTED_QUESTIONS = [
  "What is the vacation accrual policy for full-time employees?",
  "How do I submit a parental leave request?",
  "What are the remote work eligibility requirements?",
  "What does the health insurance cover for dependents?",
  "How does the performance review process work?",
];

// ─── API client ──────────────────────────────────────────────────────────────

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { "X-API-Key": API_KEY },
});

// ─── Sub-components ──────────────────────────────────────────────────────────

function SourceCard({ source, index }: { source: SourceCitation; index: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      style={{
        background: "var(--citation-bg)",
        border: "1px solid var(--citation-border)",
        borderRadius: "var(--radius-sm)",
        padding: "8px 12px",
        marginTop: 6,
        fontSize: 13,
      }}
    >
      <button
        onClick={() => setExpanded((p) => !p)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          width: "100%",
          color: "var(--accent)",
          fontWeight: 500,
          background: "none",
          border: "none",
        }}
      >
        <FileText size={13} />
        <span>[Source {source.source_id}] {source.filename}</span>
        {source.department && (
          <span style={{ color: "var(--text-secondary)", fontWeight: 400, marginLeft: 4 }}>
            · {source.department}
          </span>
        )}
        <span style={{ marginLeft: "auto", color: "var(--text-secondary)" }}>
          {(source.similarity_score * 100).toFixed(1)}%
        </span>
        {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {expanded && (
        <p style={{ marginTop: 8, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {source.excerpt}
        </p>
      )}
    </div>
  );
}

function TelemetryBadge({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        background: "var(--bg-tertiary)",
        borderRadius: 20,
        fontSize: 11,
        color: color ?? "var(--text-secondary)",
        border: "1px solid var(--border)",
      }}
    >
      {icon}
      {label}: {value}
    </span>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const [showSources, setShowSources] = useState(false);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        gap: 10,
        alignItems: "flex-start",
        maxWidth: "100%",
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: isUser ? "var(--bg-bubble-user)" : "var(--bg-tertiary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          border: "1px solid var(--border)",
        }}
      >
        {isUser ? <User size={16} /> : <Bot size={16} color="var(--accent)" />}
      </div>

      {/* Content */}
      <div style={{ maxWidth: "78%", minWidth: 0 }}>
        <div
          style={{
            background: isUser ? "var(--bg-bubble-user)" : "var(--bg-bubble-assistant)",
            border: `1px solid ${isUser ? "transparent" : "var(--border)"}`,
            borderRadius: isUser
              ? "var(--radius-lg) var(--radius-sm) var(--radius-lg) var(--radius-lg)"
              : "var(--radius-sm) var(--radius-lg) var(--radius-lg) var(--radius-lg)",
            padding: "12px 16px",
            whiteSpace: "pre-wrap",
            lineHeight: 1.65,
            fontSize: 14,
          }}
        >
          {message.flagged_for_injection && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                color: "var(--error)",
                marginBottom: 8,
                fontSize: 12,
              }}
            >
              <Shield size={13} /> Security alert: prompt injection detected
            </div>
          )}
          {message.pii_detected && !message.flagged_for_injection && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                color: "var(--warning)",
                marginBottom: 8,
                fontSize: 12,
              }}
            >
              <AlertCircle size={13} /> PII detected and redacted from your query
            </div>
          )}
          {message.content}
        </div>

        {/* Telemetry */}
        {!isUser && message.total_latency_ms !== undefined && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            <TelemetryBadge
              icon={<Clock size={10} />}
              label="Retrieval"
              value={`${message.retrieval_latency_ms?.toFixed(0)}ms`}
              color={
                (message.retrieval_latency_ms ?? 0) > 3000 ? "var(--warning)" : "var(--success)"
              }
            />
            <TelemetryBadge
              icon={<Clock size={10} />}
              label="E2E"
              value={`${message.total_latency_ms?.toFixed(0)}ms`}
              color={
                (message.total_latency_ms ?? 0) > 8000 ? "var(--error)" : "var(--text-secondary)"
              }
            />
            <TelemetryBadge
              icon={<DollarSign size={10} />}
              label="Cost"
              value={`$${message.token_cost_usd?.toFixed(5)}`}
            />
            <TelemetryBadge
              icon={<FileText size={10} />}
              label="Tokens"
              value={`${(message.prompt_tokens ?? 0) + (message.completion_tokens ?? 0)}`}
            />
          </div>
        )}

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <button
              onClick={() => setShowSources((p) => !p)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                color: "var(--accent)",
                fontSize: 12,
                fontWeight: 500,
                padding: "4px 0",
              }}
            >
              <FileText size={13} />
              {message.sources.length} source{message.sources.length !== 1 ? "s" : ""}
              {showSources ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
            {showSources && (
              <div>
                {message.sources.map((s) => (
                  <SourceCard key={s.source_id} source={s} index={s.source_id} />
                ))}
              </div>
            )}
          </div>
        )}

        <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
          {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: "var(--bg-tertiary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        <Bot size={16} color="var(--accent)" />
      </div>
      <div
        style={{
          background: "var(--bg-bubble-assistant)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm) var(--radius-lg) var(--radius-lg) var(--radius-lg)",
          padding: "16px 20px",
          display: "flex",
          gap: 5,
          alignItems: "center",
        }}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--accent)",
              animation: `bounce 1.2s infinite ${i * 0.2}s`,
              display: "inline-block",
            }}
          />
        ))}
        <style>{`
          @keyframes bounce {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
            30% { transform: translateY(-6px); opacity: 1; }
          }
        `}</style>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hello! I'm your HR Policy Assistant. I can answer questions about company policies including vacation, benefits, parental leave, remote work, performance reviews, and more.\n\nAll answers are grounded in the actual policy documents with source citations.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const sendMessage = useCallback(
    async (queryText: string) => {
      if (!queryText.trim() || isLoading) return;
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: queryText.trim(),
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setIsLoading(true);

      try {
        const { data } = await apiClient.post("/api/v1/chat/query", {
          query: queryText.trim(),
        });
        const assistantMsg: ChatMessage = {
          id: data.query_id,
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          retrieval_latency_ms: data.retrieval_latency_ms,
          total_latency_ms: data.total_latency_ms,
          token_cost_usd: data.token_cost_usd,
          prompt_tokens: data.prompt_tokens,
          completion_tokens: data.completion_tokens,
          flagged_for_injection: data.flagged_for_injection,
          pii_detected: data.pii_detected,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err: unknown) {
        const detail =
          axios.isAxiosError(err)
            ? err.response?.data?.detail ?? err.message
            : "An unexpected error occurred";
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `Error: ${detail}. Please try again.`,
            timestamp: new Date(),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setUploadStatus(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await apiClient.post("/api/v1/ingest/upload", form);
      setUploadStatus(`Uploaded "${data.filename}" — ${data.total_chunks} chunks indexed`);
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err)
        ? err.response?.data?.detail ?? err.message
        : "Upload failed";
      setUploadStatus(`Error: ${detail}`);
    } finally {
      setIsUploading(false);
      e.target.value = "";
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        background: "var(--bg-primary)",
      }}
    >
      {/* Header */}
      <header
        style={{
          background: "var(--bg-secondary)",
          borderBottom: "1px solid var(--border)",
          padding: "14px 20px",
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: "var(--radius-md)",
            background: "linear-gradient(135deg, #1f6feb, #388bfd)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Bot size={20} color="#fff" />
        </div>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
            HR Policy Assistant
          </h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            Powered by Claude Sonnet + pgvector RAG
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={handleFileUpload}
            style={{ display: "none" }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "7px 14px",
              background: "var(--bg-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-primary)",
              fontSize: 13,
              opacity: isUploading ? 0.6 : 1,
            }}
          >
            {isUploading ? <Loader2 size={14} className="spin" /> : <Upload size={14} />}
            {isUploading ? "Uploading…" : "Upload Policy"}
          </button>
        </div>
      </header>

      {/* Upload status */}
      {uploadStatus && (
        <div
          style={{
            padding: "10px 20px",
            background: uploadStatus.startsWith("Error") ? "#2d1117" : "#0d2d1a",
            borderBottom: "1px solid var(--border)",
            fontSize: 13,
            color: uploadStatus.startsWith("Error") ? "var(--error)" : "var(--success)",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          {uploadStatus.startsWith("Error") ? <AlertCircle size={14} /> : <FileText size={14} />}
          {uploadStatus}
          <button
            onClick={() => setUploadStatus(null)}
            style={{ marginLeft: "auto", color: "var(--text-muted)", fontSize: 16, lineHeight: 1 }}
          >
            ×
          </button>
        </div>
      )}

      {/* Messages */}
      <main
        className="scrollbar-thin"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "24px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 20,
          maxWidth: 860,
          width: "100%",
          margin: "0 auto",
        }}
      >
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isLoading && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </main>

      {/* Suggested questions */}
      {messages.length <= 1 && !isLoading && (
        <div
          style={{
            padding: "0 20px 12px",
            maxWidth: 860,
            width: "100%",
            margin: "0 auto",
          }}
        >
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Suggested questions
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {SUGGESTED_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => sendMessage(q)}
                style={{
                  padding: "6px 12px",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  borderRadius: 20,
                  color: "var(--text-secondary)",
                  fontSize: 12,
                  transition: "border-color 0.15s, color 0.15s",
                }}
                onMouseEnter={(e) => {
                  (e.target as HTMLButtonElement).style.borderColor = "var(--accent)";
                  (e.target as HTMLButtonElement).style.color = "var(--accent)";
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLButtonElement).style.borderColor = "var(--border)";
                  (e.target as HTMLButtonElement).style.color = "var(--text-secondary)";
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div
        style={{
          background: "var(--bg-secondary)",
          borderTop: "1px solid var(--border)",
          padding: "16px 20px",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            maxWidth: 860,
            margin: "0 auto",
            display: "flex",
            gap: 10,
            alignItems: "flex-end",
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about vacation, benefits, parental leave, remote work…"
            rows={1}
            disabled={isLoading}
            style={{
              flex: 1,
              resize: "none",
              background: "var(--bg-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
              padding: "12px 16px",
              color: "var(--text-primary)",
              fontSize: 14,
              outline: "none",
              maxHeight: 140,
              overflowY: "auto",
              transition: "border-color 0.15s",
            }}
            onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
            onInput={(e) => {
              const el = e.target as HTMLTextAreaElement;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
            }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isLoading}
            style={{
              width: 44,
              height: 44,
              borderRadius: "var(--radius-md)",
              background:
                !input.trim() || isLoading ? "var(--bg-tertiary)" : "var(--bg-bubble-user)",
              border: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: !input.trim() || isLoading ? "var(--text-muted)" : "#fff",
              transition: "background 0.15s",
              flexShrink: 0,
            }}
          >
            {isLoading ? <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} /> : <Send size={18} />}
          </button>
        </div>
        <p style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", marginTop: 8 }}>
          Answers grounded in HR policy documents · Enter to send · Shift+Enter for newline
        </p>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
