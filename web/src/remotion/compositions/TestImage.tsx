import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";

export const TestImage: React.FC<{ decomposition?: any }> = ({ decomposition }) => {
  const frame = useCurrentFrame();

  // If decomposition is provided, render its images
  if (decomposition?.scenes?.[0]?.elements) {
    const scene = decomposition.scenes[0];
    const images = scene.elements.filter((el: any) => el.type === "image" && el.content_src);

    return (
      <AbsoluteFill style={{ background: "#000", display: "flex", flexWrap: "wrap", gap: 10, padding: 20 }}>
        <div style={{ color: "white", position: "absolute", top: 5, left: 5, fontSize: 16, zIndex: 100 }}>
          Frame: {frame} | Images: {images.length}
        </div>
        {images.map((el: any, i: number) => (
          <div key={i} style={{ width: "30%", height: "40%" }}>
            <Img
              src={staticFile(el.content_src.startsWith("/") ? el.content_src.slice(1) : el.content_src)}
              style={{ width: "100%", height: "100%", objectFit: "contain" }}
            />
          </div>
        ))}
      </AbsoluteFill>
    );
  }

  // Default: single image
  const imgSrc = staticFile("data/output/08440e77/generated/s0_gen_0.png");
  return (
    <AbsoluteFill style={{ background: "#000", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ color: "white", position: "absolute", top: 10, left: 10, fontSize: 24, zIndex: 100 }}>
        Frame: {frame} | Src: {imgSrc.slice(0, 50)}
      </div>
      <Img
        src={imgSrc}
        style={{ width: "80%", height: "80%", objectFit: "contain" }}
      />
    </AbsoluteFill>
  );
};
