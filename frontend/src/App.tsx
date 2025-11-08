import { useCallback } from "react";
import Header from "./components/Header";
import InstructionPanel from "./components/InstructionPanel";
import OperationTimeline from "./components/OperationTimeline";
import PreviewPlayer from "./components/PreviewPlayer";
import ProjectToolbar from "./components/ProjectToolbar";
import UploadCard from "./components/UploadCard";
import { useProject } from "./hooks/useProject";
import "./App.css";

const App = () => {
  const { project, isUploading, isApplying, error, uploadProject, applyInstruction, exportProject } = useProject();

  const handleUpload = useCallback(
    async (file: File, name: string) => {
      await uploadProject(file, name);
    },
    [uploadProject]
  );

  return (
    <div className="app">
      <Header />
      <main className="app__body">
        {!project ? (
          <UploadCard onUpload={handleUpload} isUploading={isUploading} />
        ) : (
          <div className="workspace">
            <ProjectToolbar project={project} onExport={exportProject} />
            {error && <div className="workspace__error">{error}</div>}
            <div className="workspace__grid">
              <PreviewPlayer project={project} isProcessing={isApplying} />
              <InstructionPanel onSubmit={applyInstruction} isProcessing={isApplying} />
            </div>
            <OperationTimeline operations={project.operations} />
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
