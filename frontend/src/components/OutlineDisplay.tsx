import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { List } from "lucide-react";

interface OutlineDisplayProps {
  outline: string[];
}

export function OutlineDisplay({ outline }: OutlineDisplayProps) {
  if (!outline || outline.length === 0) {
    return null;
  }

  return (
    <Card className="bg-neutral-800 border-neutral-700 mb-4">
      <CardHeader>
        <CardTitle className="text-lg text-neutral-100 flex items-center">
          <List className="h-5 w-5 mr-2" />
          Outline
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-disc pl-5 text-neutral-300">
          {outline.map((item, index) => (
            <li key={index} className="mb-2">{item}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
} 