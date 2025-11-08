import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

export interface Operation {
  type: string;
  description: string;
  params: Record<string, number | string>;
}

export interface Project {
  id: string;
  name: string;
  status: string;
  operations: Operation[];
  preview_url?: string | null;
  current_url?: string | null;
  original_url?: string | null;
}

export interface JobStatus {
  status: string;
  error?: string | null;
}

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "",
});

export const useProject = () => {
  const [project, setProject] = useState<Project | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshProject = useCallback(async (projectId: string) => {
    const { data } = await client.get<{ project: Project }>(`/api/projects/${projectId}`);
    setProject(data.project);
  }, []);

  const uploadProject = useCallback(async (file: File, name: string) => {
    setIsUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("name", name);
      const { data } = await client.post<{ project: Project }>("/api/projects", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setProject(data.project);
      return data.project;
    } catch (err) {
      setError("Failed to upload video");
      throw err;
    } finally {
      setIsUploading(false);
    }
  }, []);

  const applyInstruction = useCallback(
    async (prompt: string, preview = true) => {
      if (!project) {
        throw new Error("No project loaded");
      }
      setIsApplying(true);
      setError(null);
      try {
        const { data } = await client.post<{ job: { job_id: string }; project: Project }>(
          `/api/projects/${project.id}/instructions`,
          { prompt, preview }
        );
        setProject(data.project);
        setJobId(data.job.job_id);
        setJobStatus({ status: "processing" });
      } catch (err) {
        setError("Failed to interpret instruction");
        setIsApplying(false);
        throw err;
      }
    },
    [project]
  );

  useEffect(() => {
    if (!jobId || !project) return;

    const interval = window.setInterval(async () => {
      try {
        const { data } = await client.get<JobStatus>(`/api/jobs/${jobId}`);
        setJobStatus(data);
        if (data.status === "completed") {
          await refreshProject(project.id);
          setIsApplying(false);
          setJobId(null);
        }
        if (data.status === "failed" || data.status === "unknown") {
          setError(data.error ?? "Instruction failed");
          setIsApplying(false);
          setJobId(null);
        }
      } catch (err) {
        setError("Unable to retrieve job status");
        setIsApplying(false);
        setJobId(null);
      }
    }, 1800);

    return () => window.clearInterval(interval);
  }, [jobId, project, refreshProject]);

  const exportProject = useCallback(
    async (format: "mp4" | "mov") => {
      if (!project) return;
      const { data } = await client.post(`/api/projects/${project.id}/export`, { format }, {
        responseType: "blob",
      });
      const blob = new Blob([data], { type: format === "mp4" ? "video/mp4" : "video/quicktime" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${project.name}.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
    },
    [project]
  );

  const reset = useCallback(() => {
    setProject(null);
    setJobId(null);
    setJobStatus(null);
    setError(null);
  }, []);

  return useMemo(
    () => ({
      project,
      jobStatus,
      isUploading,
      isApplying,
      error,
      uploadProject,
      applyInstruction,
      refreshProject,
      exportProject,
      reset,
    }),
    [
      project,
      jobStatus,
      isUploading,
      isApplying,
      error,
      uploadProject,
      applyInstruction,
      refreshProject,
      exportProject,
      reset,
    ]
  );
};
