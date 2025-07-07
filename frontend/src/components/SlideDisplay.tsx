import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChevronLeft, ChevronRight, Presentation } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";

interface SlideData {
  slide_id: number;
  title: string;
  content: string;
  outline_topic: string;
}

interface SlideDisplayProps {
  slides: SlideData[];
  mdComponents: any;
}

export function SlideDisplay({ slides, mdComponents }: SlideDisplayProps) {
  const [currentSlide, setCurrentSlide] = useState(0);

  if (!slides || slides.length === 0) {
    return null;
  }

  // Sort slides by slide_id to ensure proper order
  const sortedSlides = [...slides].sort((a, b) => a.slide_id - b.slide_id);

  const goToNextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % sortedSlides.length);
  };

  const goToPrevSlide = () => {
    setCurrentSlide((prev) => (prev - 1 + sortedSlides.length) % sortedSlides.length);
  };

  const currentSlideData = sortedSlides[currentSlide];

  return (
    <div className="w-full max-w-4xl mx-auto">
      {/* Slide Counter */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Presentation className="h-5 w-5 text-neutral-400" />
          <span className="text-sm text-neutral-400">
            Presentation ({slides.length} slides)
          </span>
        </div>
        <div className="text-sm text-neutral-400">
          {currentSlide + 1} / {sortedSlides.length}
        </div>
      </div>

      {/* Main Slide */}
      <Card className="bg-neutral-800 border-neutral-700">
        <CardHeader>
          <CardTitle className="text-xl text-neutral-100">
            {currentSlideData.title}
          </CardTitle>
          <div className="text-xs text-neutral-500">
            Topic: {currentSlideData.outline_topic}
          </div>
        </CardHeader>
        <CardContent>
          <div className="prose prose-invert max-w-none">
            <ReactMarkdown components={mdComponents}>
              {currentSlideData.content}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex items-center justify-between mt-4">
        <Button
          variant="outline"
          size="sm"
          onClick={goToPrevSlide}
          disabled={sortedSlides.length <= 1}
          className="border-neutral-600 text-neutral-300 hover:bg-neutral-700"
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Previous
        </Button>

        {/* Slide Dots */}
        <div className="flex gap-2">
          {sortedSlides.map((_, index) => (
            <button
              key={index}
              onClick={() => setCurrentSlide(index)}
              className={cn(
                "w-3 h-3 rounded-full transition-colors",
                index === currentSlide
                  ? "bg-neutral-400"
                  : "bg-neutral-600 hover:bg-neutral-500"
              )}
            />
          ))}
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={goToNextSlide}
          disabled={sortedSlides.length <= 1}
          className="border-neutral-600 text-neutral-300 hover:bg-neutral-700"
        >
          Next
          <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>

      {/* Slide List */}
      <div className="mt-6">
        <h3 className="text-lg font-semibold text-neutral-200 mb-3">All Slides</h3>
        <div className="grid gap-3">
          {sortedSlides.map((slide, index) => (
            <Card
              key={slide.slide_id}
              className={cn(
                "cursor-pointer transition-colors border-neutral-700",
                index === currentSlide
                  ? "bg-neutral-700 border-neutral-600"
                  : "bg-neutral-800 hover:bg-neutral-750"
              )}
              onClick={() => setCurrentSlide(index)}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-neutral-200 text-sm">
                      {slide.title}
                    </h4>
                    <p className="text-xs text-neutral-500 mt-1">
                      {slide.outline_topic}
                    </p>
                  </div>
                  <div className="text-xs text-neutral-500">
                    Slide {slide.slide_id + 1}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
} 