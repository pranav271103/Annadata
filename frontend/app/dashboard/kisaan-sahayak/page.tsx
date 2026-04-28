"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_PREFIXES } from "@/lib/utils";

// ----------------------------------------------------------------
// Quick action presets (covers all 7 KB intents + general)
// ----------------------------------------------------------------
const quickActions = [
  { label: "Wheat fertilizer", message: "What fertilizer should I use for wheat?" },
  { label: "Rice irrigation", message: "When should I irrigate rice?" },
  { label: "Pest control (maize)", message: "How to control stem borer in maize?" },
  { label: "Government schemes", message: "Tell me about PM-KISAN and other schemes" },
  { label: "Sowing guide (mustard)", message: "Best sowing time and method for mustard?" },
  { label: "Harvest advice (potato)", message: "When to harvest potato and storage tips?" },
  { label: "Market prices (cotton)", message: "What are current cotton market prices and MSP?" },
  { label: "Weather advisory", message: "What is the weather forecast and irrigation advice?" },
] as const;

// ----------------------------------------------------------------
// Types
// ----------------------------------------------------------------
interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  modelUsed?: string;
  suggestedActions?: string[];
}

interface ChatAPIResponse {
  session_id: string;
  response: string;
  language: string;
  intent_detected: string;
  crop_detected: string | null;
  sources: { type: string; topic: string }[];
  suggested_actions: string[];
  model_used: string;
  responded_at: string;
}

// ----------------------------------------------------------------
// Simple markdown-ish renderer for assistant messages
// ----------------------------------------------------------------
function FormattedMessage({ text }: { text: string }) {
  // Split by double newlines for paragraphs, single newlines for line breaks
  const paragraphs = text.split(/\n{2,}/);

  return (
    <div className="space-y-2">
      {paragraphs.map((para, pi) => {
        // Check if this paragraph is a bullet list
        const lines = para.split("\n");
        const isList = lines.every(
          (l) => l.trim().startsWith("- ") || l.trim().startsWith("* ") || /^\d+\.\s/.test(l.trim()) || l.trim() === ""
        );

        if (isList) {
          return (
            <ul key={pi} className="space-y-1 pl-4">
              {lines
                .filter((l) => l.trim())
                .map((line, li) => {
                  const content = line.replace(/^\s*[-*]\s+/, "").replace(/^\d+\.\s+/, "");
                  return (
                    <li key={li} className="list-disc text-sm">
                      <FormatInline text={content} />
                    </li>
                  );
                })}
            </ul>
          );
        }

        return (
          <p key={pi} className="text-sm">
            {lines.map((line, li) => (
              <span key={li}>
                {li > 0 && <br />}
                <FormatInline text={line} />
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

/** Handles **bold** and *italic* inline formatting */
function FormatInline({ text }: { text: string }) {
  // Match **bold**, *italic*, and plain text segments
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className="font-semibold">
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith("*") && part.endsWith("*")) {
          return <em key={i}>{part.slice(1, -1)}</em>;
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

// ----------------------------------------------------------------
// Typing indicator (3 bouncing dots)
// ----------------------------------------------------------------
function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1 rounded-lg bg-[var(--color-border)] px-4 py-3">
        <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-text-muted)] [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-text-muted)] [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-text-muted)] [animation-delay:300ms]" />
      </div>
    </div>
  );
}

// ----------------------------------------------------------------
// Main component
// ----------------------------------------------------------------
export default function KisaanSahayakPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [isListening, setIsListening] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      setMessages((prev) => [...prev, { role: "user", content: text.trim() }]);
      setInput("");
      setStatus("loading");
      try {
        const res = await fetch(`${API_PREFIXES.kisaanSahayak}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text.trim(),
            language: "en",
            session_id: sessionId,
          }),
        });
        if (!res.ok) throw new Error("Chat failed");
        const data: ChatAPIResponse = await res.json();
        setSessionId(data.session_id ?? sessionId);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.response ?? "Response received",
            modelUsed: data.model_used,
            suggestedActions: data.suggested_actions,
          },
        ]);
        setStatus("idle");
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Sorry, I could not reach the Kisaan Sahayak service. Please try again.",
          },
        ]);
        setStatus("error");
      }
    },
    [sessionId]
  );

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  const [speechSupported, setSpeechSupported] = useState(false);

  useEffect(() => {
    setSpeechSupported(typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window));
  }, []);

  function toggleVoice() {
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.lang = "hi-IN"; // Hindi primary, also picks up English
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) {
        setInput((prev) => (prev ? prev + " " + transcript : transcript));
      }
    };

    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }

  return (
    <div className="flex h-full flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-[var(--color-text)]">
          Kisaan Sahayak &mdash; AI Assistant
        </h1>
        <p className="mt-1 text-[var(--color-text-muted)]">
          The official Annadata OS agricultural assistant &mdash; powered by Team Annadata to help you with
          fertilizers, irrigation, pest control, and government schemes.
        </p>
      </div>

      <div className="grid flex-1 gap-4 lg:grid-cols-[1fr_320px]">
        {/* Chat area */}
        <Card className="flex flex-col">
          <CardHeader className="border-b border-[var(--color-border)]">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Chat</CardTitle>
              <div className="flex items-center gap-2">
                {sessionId && (
                  <span className="text-xs text-[var(--color-text-muted)] font-mono">
                    {sessionId.slice(0, 16)}
                  </span>
                )}
                <Badge variant="outline" className="text-xs">
                  {status === "loading" ? "Thinking..." : "Online"}
                </Badge>
              </div>
            </div>
          </CardHeader>

          {/* Messages */}
          <CardContent className="flex-1 overflow-y-auto pt-4">
            {messages.length === 0 && status !== "loading" ? (
              <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-3 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--color-primary)]/10">
                  <svg
                    className="h-8 w-8 text-[var(--color-primary)]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                    />
                  </svg>
                </div>
                <div>
                  <p className="font-medium text-[var(--color-text)]">
                    Namaste Kisaan!
                  </p>
                  <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
                    Ask me anything about farming — fertilizer dosage, irrigation
                    schedules, pest management, government schemes, or market prices.
                    Try a quick action to get started.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((msg, i) => (
                  <div key={i}>
                    <div
                      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-lg px-4 py-2.5 ${msg.role === "user"
                          ? "bg-[var(--color-primary)] text-white"
                          : "bg-[var(--color-border)] text-[var(--color-text)]"
                          }`}
                      >
                        {msg.role === "assistant" ? (
                          <FormattedMessage text={msg.content} />
                        ) : (
                          <p className="text-sm">{msg.content}</p>
                        )}
                      </div>
                    </div>
                    {/* Model badge + suggested actions for assistant messages */}
                    {msg.role === "assistant" && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-1">
                        {msg.modelUsed && (
                          <Badge
                            variant="outline"
                            className={`text-[10px] border-[var(--color-primary)] text-[var(--color-primary)]`}
                          >
                            Annadata Support
                          </Badge>
                        )}
                        {msg.suggestedActions?.map((action, ai) => (
                          <button
                            key={ai}
                            onClick={() => sendMessage(action)}
                            className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-0.5 text-[11px] text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
                          >
                            {action}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {status === "loading" && <TypingIndicator />}
                <div ref={messagesEndRef} />
              </div>
            )}
          </CardContent>

          {/* Input */}
          <div className="border-t border-[var(--color-border)] p-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about fertilizers, irrigation, schemes..."
                disabled={status === "loading"}
                className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] disabled:opacity-50"
              />
              {speechSupported && (
                <button
                  onClick={toggleVoice}
                  disabled={status === "loading"}
                  className={`rounded-lg border px-3 py-2 text-sm transition-colors ${isListening
                    ? "border-red-500 bg-red-500/10 text-red-500 animate-pulse"
                    : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)]"
                    } disabled:opacity-50`}
                  title={isListening ? "Stop listening" : "Voice input (Hindi/English)"}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" x2="12" y1="19" y2="22" /></svg>
                </button>
              )}
              <Button
                onClick={() => sendMessage(input)}
                disabled={status === "loading" || !input.trim()}
              >
                {status === "loading" ? "..." : "Send"}
              </Button>
            </div>
            {status === "error" && (
              <p className="mt-2 text-xs text-[var(--color-warning)]">
                Service may be offline. Responses may be delayed.
              </p>
            )}
          </div>
        </Card>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Quick actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Quick Actions</CardTitle>
              <CardDescription>Tap to ask a common question</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-2">
                {quickActions.map((action) => (
                  <Button
                    key={action.label}
                    variant="outline"
                    size="sm"
                    className="justify-start text-left"
                    disabled={status === "loading"}
                    onClick={() => sendMessage(action.message)}
                  >
                    {action.label}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Session info */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Session Info</CardTitle>
              <CardDescription>Current conversation details</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-text-muted)]">Messages</span>
                <span className="font-medium text-[var(--color-text)]">
                  {messages.length}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-text-muted)]">Session</span>
                <span className="font-mono text-xs text-[var(--color-text)]">
                  {sessionId ? sessionId.slice(0, 12) + "..." : "New"}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-text-muted)]">Model</span>
                <Badge variant="outline" className="text-[10px]">
                  {messages.length > 0
                    ? (messages.filter((m) => m.role === "assistant").pop()?.modelUsed ?? "rule-based")
                    : "Annadata AI"}
                </Badge>
              </div>
              {messages.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2 w-full"
                  onClick={() => {
                    setMessages([]);
                    setSessionId(null);
                    setStatus("idle");
                  }}
                >
                  New conversation
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Multi-Agent AI Pipeline */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Multi-Agent Pipeline */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Multi-Agent Pipeline</CardTitle>
            <CardDescription>
              Orchestrated analysis using multiple specialized AI agents
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text-muted)]">
              Submit a farm query and receive a comprehensive analysis
              orchestrated across vision, weather, market, and memory agents.
              Each agent contributes domain-specific insights that are
              synthesized into a unified recommendation.
            </p>
            <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Automated multi-agent orchestration pipeline
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Synthesized cross-domain recommendations
              </li>
            </ul>
            <div className="mt-4">
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                POST /pipeline/analyze
              </code>
            </div>
          </CardContent>
        </Card>

        {/* Vision Agent */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Vision Agent</CardTitle>
            <CardDescription>
              Image-based crop and field analysis
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text-muted)]">
              Analyze field images using computer vision to detect crop health
              status, growth stage, weed pressure, and visible nutrient
              deficiencies. Supports satellite imagery and phone camera uploads.
            </p>
            <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Multi-model image classification and segmentation
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Detects visual anomalies and stress indicators
              </li>
            </ul>
            <div className="mt-4">
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                POST /agent/vision
              </code>
            </div>
          </CardContent>
        </Card>

        {/* Weather Agent */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Weather Agent</CardTitle>
            <CardDescription>
              Hyper-local weather intelligence for farming decisions
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text-muted)]">
              Provides localized weather forecasts, historical trends, and
              agro-meteorological advisories tailored to your crop type and
              growth stage. Includes frost, heatwave, and rainfall alerts.
            </p>
            <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                7-day and seasonal forecast with confidence intervals
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Extreme weather early warning system
              </li>
            </ul>
            <div className="mt-4">
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                GET /agent/weather
              </code>
            </div>
          </CardContent>
        </Card>

        {/* Market Agent */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Market Agent</CardTitle>
            <CardDescription>
              Real-time market prices and demand intelligence
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text-muted)]">
              Access live mandi prices, demand trends, and optimal selling
              strategies. The market agent aggregates data from multiple mandis
              and provides price forecasts to help time your sales.
            </p>
            <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Multi-mandi price comparison and trend analysis
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Demand forecasting and sell-timing signals
              </li>
            </ul>
            <div className="mt-4">
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                GET /agent/market
              </code>
            </div>
          </CardContent>
        </Card>

        {/* Memory Agent */}
        <Card className="sm:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Memory Agent</CardTitle>
            <CardDescription>
              Persistent farmer interaction history and context management
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text-muted)]">
              Logs all farmer interactions, recommendations, and outcomes to
              build a persistent knowledge base. Retrieves historical context to
              personalize future recommendations and track farming decisions over
              time.
            </p>
            <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Logs interactions with timestamps and context metadata
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Retrieves full interaction history per farmer
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Enables personalized, context-aware recommendations
              </li>
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                POST /agent/memory/log
              </code>
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                GET /agent/memory/&#123;farmer_id&#125;
              </code>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
