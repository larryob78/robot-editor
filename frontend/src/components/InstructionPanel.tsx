import { FormEvent, useState } from "react";
import "./InstructionPanel.css";

interface InstructionPanelProps {
  onSubmit: (prompt: string, preview: boolean) => Promise<void>;
  isProcessing: boolean;
}

const suggestions = [
  "Trim to the first 30 seconds and brighten the footage",
  "Slow down by 0.5x and highlight the second segment",
  "Increase volume by 20% and remove silence",
];

const InstructionPanel = ({ onSubmit, isProcessing }: InstructionPanelProps) => {
  const [prompt, setPrompt] = useState("");
  const [generatePreview, setGeneratePreview] = useState(true);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;
    await onSubmit(prompt, generatePreview);
    setPrompt("");
  };

  return (
    <section className="instruction-panel">
      <header>
        <h2>Direct the cut</h2>
        <p>Describe the edit you'd like. The agent interprets and applies it for you.</p>
      </header>
      <form onSubmit={handleSubmit}>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Trim the intro, brighten the colors, and speed up the outro by 2x"
          rows={4}
        />
        <div className="instruction-panel__toolbar">
          <label>
            <input
              type="checkbox"
              checked={generatePreview}
              onChange={(event) => setGeneratePreview(event.target.checked)}
            />
            Generate lightweight preview
          </label>
          <button type="submit" disabled={!prompt.trim() || isProcessing}>
            {isProcessing ? "Thinking..." : "Apply instruction"}
          </button>
        </div>
      </form>
      <ul className="instruction-panel__suggestions">
        {suggestions.map((item) => (
          <li key={item}>
            <button type="button" onClick={() => setPrompt(item)}>
              {item}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default InstructionPanel;
