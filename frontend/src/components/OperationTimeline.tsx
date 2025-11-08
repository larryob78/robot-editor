import { Operation } from "../hooks/useProject";
import "./OperationTimeline.css";

interface OperationTimelineProps {
  operations: Operation[];
}

const OperationTimeline = ({ operations }: OperationTimelineProps) => (
  <section className="operation-timeline">
    <header>
      <h2>Agent reasoning</h2>
      <p>Every transformation derived from your natural language prompts.</p>
    </header>
    {operations.length === 0 ? (
      <div className="operation-timeline__empty">No operations yet. Ask the agent to make the first move.</div>
    ) : (
      <ol>
        {operations.map((operation, index) => (
          <li key={`${operation.type}-${index}`}>
            <span className="operation-timeline__step">{index + 1}</span>
            <div>
              <h3>{operation.description}</h3>
              <pre>{JSON.stringify(operation.params, null, 2)}</pre>
            </div>
          </li>
        ))}
      </ol>
    )}
  </section>
);

export default OperationTimeline;
