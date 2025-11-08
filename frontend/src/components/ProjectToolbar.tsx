import { Project } from "../hooks/useProject";
import "./ProjectToolbar.css";

interface ProjectToolbarProps {
  project: Project;
  onExport: (format: "mp4" | "mov") => Promise<void>;
}

const ProjectToolbar = ({ project, onExport }: ProjectToolbarProps) => (
  <section className="project-toolbar">
    <div>
      <h2>{project.name}</h2>
      <p>Project ID: {project.id}</p>
    </div>
    <div className="project-toolbar__actions">
      <button type="button" onClick={() => void onExport("mp4") }>
        Export MP4
      </button>
      <button type="button" onClick={() => void onExport("mov") }>
        Export MOV
      </button>
    </div>
  </section>
);

export default ProjectToolbar;
