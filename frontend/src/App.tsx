import { useStream } from "@langchain/langgraph-sdk/react";
import type { Message } from "@langchain/langgraph-sdk";
import { useState, useEffect, useRef, useCallback } from "react";
import { ProcessedEvent } from "@/components/ActivityTimeline";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { ChatMessagesView } from "@/components/ChatMessagesView";
import { Button } from "@/components/ui/button";

export default function App() {
  const [processedEventsTimeline, setProcessedEventsTimeline] = useState<
    ProcessedEvent[]
  >([]);
  const [historicalActivities, setHistoricalActivities] = useState<
    Record<string, ProcessedEvent[]>
  >({});
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const hasFinalizeEventOccurredRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const thread = useStream<{
    messages: Message[];
    initial_search_query_count: number;
    max_research_loops: number;
    reasoning_model: string;
  }>({
    apiUrl: import.meta.env.DEV
      ? "http://localhost:2024"
      : "http://localhost:8123",
    assistantId: "agent",
    messagesKey: "messages",
    onUpdateEvent: (event: any) => {
      // Add debugging to see what events we're receiving
      console.log("Received LangGraph event:", event);
      
      let processedEvent: ProcessedEvent | null = null;
      
      // Handle new node-based events from the updated graph structure
      if (event.decision_maker) {
        const taskData = event.decision_maker;
        let taskName = "Unknown Task";
        let taskDescription = "Making a decision on next steps";
        
        console.log("Decision maker event:", taskData);
        
        if (taskData.next_task) {
          if (typeof taskData.next_task === "string") {
            taskName = taskData.next_task;
            switch (taskData.next_task) {
              case "ContextSearch":
                taskDescription = "Initiating web research to gather information";
                break;
              case "GenerateOutline":
                taskDescription = "Creating presentation outline structure";
                break;
              case "GenerateSlides":
                taskDescription = "Generating slide content";
                break;
              default:
                taskDescription = `Proceeding with ${taskData.next_task}`;
            }
          } else if (taskData.next_task && taskData.next_task.response) {
            // FinalResponse object - this means the workflow will end soon
            taskName = "Final Answer";
            taskDescription = "Providing final response";
            console.log("Final response detected, setting finalize flag");
            hasFinalizeEventOccurredRef.current = true;
          }
        }
        
        processedEvent = {
          title: `Decision: ${taskName}`,
          data: taskData.reasoning || taskDescription,
        };
      } else if (event.generate_query) {
        const queries = event.generate_query.query_list || [];
        const queryTexts = queries.map((q: any) => q.query || q).join(", ");
        processedEvent = {
          title: "Generating Search Queries",
          data: queryTexts || "Creating search queries for research",
        };
      } else if (event.web_research) {
        const sources = event.web_research.sources_gathered || [];
        const numSources = sources.length;
        const searchQuery = event.web_research.search_query?.[0] || "research topic";
        processedEvent = {
          title: "Web Research",
          data: `Researching "${searchQuery}" - Gathered ${numSources} sources`,
        };
      } else if (event.reflection) {
        const reflectionData = event.reflection;
        let analysisResult = "Analyzing research results";
        
        if (reflectionData.is_sufficient !== undefined) {
          if (reflectionData.is_sufficient) {
            analysisResult = "Research complete - sufficient information gathered";
          } else {
            const gapInfo = reflectionData.knowledge_gap ? ` - ${reflectionData.knowledge_gap}` : "";
            analysisResult = `Need more research${gapInfo}`;
          }
        }
        
        processedEvent = {
          title: "Reflection",
          data: analysisResult,
        };
      } else if (event.generate_outline) {
        const outlineData = event.generate_outline;
        const numOutlines = outlineData.unused_outline_list?.length || 0;
        const message = outlineData.task_message?.[0] || `Generated ${numOutlines} slide outlines`;
        
        processedEvent = {
          title: "Generating Outline",
          data: message,
        };
      } else if (event.generate_slide_content) {
        const slideData = event.generate_slide_content;
        const slideCount = slideData.slides?.length || 0;
        const topic = slideData.processed_outline_list?.[0] || "slide content";
        const message = slideData.task_message?.[0] || `Generated ${slideCount} slide(s) for "${topic}"`;
        
        processedEvent = {
          title: "Generating Slide Content",
          data: message,
        };
      } else if (event.cleanup_outline_list) {
        processedEvent = {
          title: "Processing Outlines",
          data: "Organizing outline structure",
        };
      } else if (event.reset_task_messages) {
        processedEvent = {
          title: "Finalizing",
          data: "Completing workflow and cleaning up",
        };
        // Don't set finalize flag here - it should already be set by decision_maker
        console.log("Reset task messages event - workflow completing");
      }
      
      if (processedEvent) {
        console.log("Adding processed event to timeline:", processedEvent);
        setProcessedEventsTimeline((prevEvents) => {
          const newEvents = [...prevEvents, processedEvent!];
          console.log("Updated timeline events:", newEvents);
          return newEvents;
        });
      } else {
        console.log("No processed event created for:", event);
      }
    },
    onError: (error: any) => {
      setError(error.message);
    },
  });

  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollViewport = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]"
      );
      if (scrollViewport) {
        scrollViewport.scrollTop = scrollViewport.scrollHeight;
      }
    }
  }, [thread.messages]);

  useEffect(() => {
    console.log("Finalization useEffect triggered:", {
      hasFinalizeEvent: hasFinalizeEventOccurredRef.current,
      isLoading: thread.isLoading,
      messagesLength: thread.messages.length,
      timelineLength: processedEventsTimeline.length
    });
    
    if (
      hasFinalizeEventOccurredRef.current &&
      !thread.isLoading &&
      thread.messages.length > 0
    ) {
      const lastMessage = thread.messages[thread.messages.length - 1];
      console.log("Last message:", lastMessage);
      
      if (lastMessage && lastMessage.type === "ai" && lastMessage.id) {
        console.log("Saving timeline to historical activities:", processedEventsTimeline);
        setHistoricalActivities((prev) => ({
          ...prev,
          [lastMessage.id!]: [...processedEventsTimeline],
        }));
        console.log("Timeline saved, resetting finalize flag");
      }
      hasFinalizeEventOccurredRef.current = false;
    }
  }, [thread.messages, thread.isLoading, processedEventsTimeline]);

  const handleSubmit = useCallback(
    (submittedInputValue: string, effort: string, model: string) => {
      if (!submittedInputValue.trim()) return;
      console.log("Clearing timeline for new submission");
      setProcessedEventsTimeline([]);
      hasFinalizeEventOccurredRef.current = false;

      // convert effort to, initial_search_query_count and max_research_loops
      // low means max 1 loop and 1 query
      // medium means max 3 loops and 3 queries
      // high means max 10 loops and 5 queries
      let initial_search_query_count = 0;
      let max_research_loops = 0;
      switch (effort) {
        case "low":
          initial_search_query_count = 1;
          max_research_loops = 1;
          break;
        case "medium":
          initial_search_query_count = 3;
          max_research_loops = 3;
          break;
        case "high":
          initial_search_query_count = 5;
          max_research_loops = 10;
          break;
      }

      const newMessages: Message[] = [
        ...(thread.messages || []),
        {
          type: "human",
          content: submittedInputValue,
          id: Date.now().toString(),
        },
      ];
      thread.submit({
        messages: newMessages,
        initial_search_query_count: initial_search_query_count,
        max_research_loops: max_research_loops,
        reasoning_model: model,
      });
    },
    [thread]
  );

  const handleCancel = useCallback(() => {
    thread.stop();
    window.location.reload();
  }, [thread]);

  return (
    <div className="flex h-screen bg-neutral-800 text-neutral-100 font-sans antialiased">
      <main className="h-full w-full max-w-4xl mx-auto">
          {thread.messages.length === 0 ? (
            <WelcomeScreen
              handleSubmit={handleSubmit}
              isLoading={thread.isLoading}
              onCancel={handleCancel}
            />
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="flex flex-col items-center justify-center gap-4">
                <h1 className="text-2xl text-red-400 font-bold">Error</h1>
                <p className="text-red-400">{JSON.stringify(error)}</p>

                <Button
                  variant="destructive"
                  onClick={() => window.location.reload()}
                >
                  Retry
                </Button>
              </div>
            </div>
          ) : (
            <ChatMessagesView
              messages={thread.messages}
              isLoading={thread.isLoading}
              scrollAreaRef={scrollAreaRef}
              onSubmit={handleSubmit}
              onCancel={handleCancel}
              liveActivityEvents={processedEventsTimeline}
              historicalActivities={historicalActivities}
            />
          )}
      </main>
    </div>
  );
}
