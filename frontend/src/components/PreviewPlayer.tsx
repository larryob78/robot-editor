import { Project } from "../hooks/useProject";
import "./PreviewPlayer.css";

interface PreviewPlayerProps {
  project: Project;
  isProcessing: boolean;
}

const PreviewPlayer = ({ project, isProcessing }: PreviewPlayerProps) => {
  const source = project.preview_url ?? project.current_url ?? project.original_url ?? undefined;

  return (
    <section className="preview-player">
      <header>
        <div>
          <h2>Live preview</h2>
          <p>{project.status === "processing" || isProcessing ? "Applying your instruction..." : "Latest agent cut"}</p>
        </div>
        <span className={`preview-player__status preview-player__status--${project.status}`}>
          {project.status}
        </span>
      </header>
      {source ? (
        <video
          key={source}
          controls
          muted
          playsInline
          src={source}
          className={`preview-player__video ${isProcessing ? "preview-player__video--loading" : ""}`.trim()}
        />
      ) : (
        <div className="preview-player__placeholder">
          <span>No preview yet. Apply an instruction to generate one.</span>
        </div>
      )}
    </section>
  );
};

export default PreviewPlayer;
