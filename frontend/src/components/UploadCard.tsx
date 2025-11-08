import { ChangeEvent, FormEvent, useRef, useState } from "react";
import "./UploadCard.css";

interface UploadCardProps {
  onUpload: (file: File, name: string) => Promise<void>;
  isUploading: boolean;
}

const ACCEPTED_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-matroska",
  "video/webm",
];

const UploadCard = ({ onUpload, isUploading }: UploadCardProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("Untitled Project");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) {
      setFile(selected);
      setName(selected.name.replace(/\.[^/.]+$/, ""));
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      inputRef.current?.focus();
      return;
    }
    await onUpload(file, name);
  };

  return (
    <form className="upload-card" onSubmit={handleSubmit}>
      <div className="upload-card__dropzone" onClick={() => inputRef.current?.click()}>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          onChange={handleFileChange}
          style={{ display: "none" }}
        />
        <div className="upload-card__icon">⬆️</div>
        <h2>Drop your footage or browse files</h2>
        <p>Supported formats: MP4, MOV, AVI, MKV, WEBM</p>
        {file && <span className="upload-card__filename">{file.name}</span>}
      </div>
      <label className="upload-card__label">
        Project name
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Product teaser" />
      </label>
      <button type="submit" disabled={!file || isUploading}>
        {isUploading ? "Uploading..." : "Create project"}
      </button>
    </form>
  );
};

export default UploadCard;
