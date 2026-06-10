import React, { useCallback, useRef, useState } from "react";

interface FileDropZoneProps {
  files: File[];
  onChange: (files: File[]) => void;
  accept?: string;
  label: string;
  hint?: string;
  maxFiles?: number;
}

export function FileDropZone({
  files,
  onChange,
  accept = "image/*,video/*",
  label,
  hint,
  maxFiles = 20,
}: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback(
    (newFiles: FileList | File[]) => {
      const incoming = Array.from(newFiles);
      // Dedupe by name+size
      const existing = new Set(files.map((f) => `${f.name}_${f.size}`));
      const unique = incoming.filter((f) => !existing.has(`${f.name}_${f.size}`));
      const merged = [...files, ...unique].slice(0, maxFiles);
      onChange(merged);
    },
    [files, onChange, maxFiles]
  );

  const removeFile = useCallback(
    (index: number) => {
      const next = files.filter((_, i) => i !== index);
      onChange(next);
    },
    [files, onChange]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles]
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
  }, []);

  const isVideo = (f: File) => f.type.startsWith("video/");
  const isImage = (f: File) => f.type.startsWith("image/");

  // Generate thumbnail URL for images
  const thumbUrl = (f: File) => {
    if (isImage(f)) return URL.createObjectURL(f);
    return null;
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  return (
    <div style={s.wrapper}>
      {/* Drop zone */}
      <div
        style={{
          ...s.dropzone,
          ...(dragging ? s.dropzoneActive : {}),
        }}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = ""; // reset so same file can be re-selected
          }}
        />
        <div style={s.dropIcon}>{dragging ? "📥" : "📁"}</div>
        <div style={s.dropLabel}>{label}</div>
        <div style={s.dropHint}>
          {hint || "拖拽文件到这里，或点击选择"}
        </div>
        {files.length > 0 && (
          <div style={s.countBadge}>
            {files.length} 个文件
          </div>
        )}
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div style={s.fileList}>
          {files.map((f, i) => {
            const url = thumbUrl(f);
            return (
              <div key={`${f.name}_${f.size}_${i}`} style={s.fileCard}>
                {/* Thumbnail or icon */}
                <div style={s.thumb}>
                  {url ? (
                    <img src={url} alt={f.name} style={s.thumbImg} />
                  ) : isVideo(f) ? (
                    <span style={s.thumbIcon}>🎬</span>
                  ) : (
                    <span style={s.thumbIcon}>📄</span>
                  )}
                </div>

                {/* Info */}
                <div style={s.fileInfo}>
                  <div style={s.fileName}>{f.name}</div>
                  <div style={s.fileSize}>{formatSize(f.size)}</div>
                </div>

                {/* Remove */}
                <button
                  style={s.removeBtn}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(i);
                  }}
                  title="移除"
                >
                  ✕
                </button>
              </div>
            );
          })}

          {/* Add more button */}
          {files.length < maxFiles && (
            <div
              style={s.addMore}
              onClick={() => inputRef.current?.click()}
            >
              <span style={{ fontSize: 20 }}>+</span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                添加更多
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  wrapper: {
    flex: 1,
    minWidth: 200,
  },
  dropzone: {
    border: "2px dashed var(--border)",
    borderRadius: 10,
    padding: "24px 16px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    cursor: "pointer",
    transition: "all 0.2s",
    background: "var(--bg-input)",
    minHeight: 120,
    position: "relative",
  },
  dropzoneActive: {
    borderColor: "var(--accent)",
    background: "rgba(59,130,246,0.06)",
    transform: "scale(1.01)",
  },
  dropIcon: {
    fontSize: 28,
    marginBottom: 4,
  },
  dropLabel: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "-0.01em",
  },
  dropHint: {
    fontSize: 11,
    color: "var(--text-muted)",
    textAlign: "center",
  },
  countBadge: {
    position: "absolute",
    top: 8,
    right: 8,
    fontSize: 10,
    fontWeight: 700,
    color: "var(--accent)",
    background: "rgba(59,130,246,0.1)",
    border: "1px solid rgba(59,130,246,0.2)",
    borderRadius: 10,
    padding: "2px 8px",
    fontFamily: "var(--font-mono)",
  },
  fileList: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginTop: 10,
  },
  fileCard: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "6px 10px",
    maxWidth: 200,
    transition: "border-color 0.15s",
  },
  thumb: {
    width: 36,
    height: 36,
    borderRadius: 6,
    overflow: "hidden",
    background: "var(--bg-root)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  thumbImg: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  thumbIcon: {
    fontSize: 18,
  },
  fileInfo: {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
  },
  fileName: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-primary)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  fileSize: {
    fontSize: 10,
    color: "var(--text-muted)",
    fontFamily: "var(--font-mono)",
  },
  removeBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-muted)",
    fontSize: 14,
    cursor: "pointer",
    padding: "2px 4px",
    borderRadius: 4,
    transition: "all 0.15s",
    lineHeight: 1,
    flexShrink: 0,
  },
  addMore: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
    width: 80,
    height: 52,
    border: "1px dashed var(--border)",
    borderRadius: 8,
    cursor: "pointer",
    transition: "all 0.15s",
    background: "transparent",
  },
};
