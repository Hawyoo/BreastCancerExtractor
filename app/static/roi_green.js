(() => {
  // editor_interactions.js intentionally owns all geometry and hit-testing.
  // This small final layer only changes ROI presentation: draft and active
  // transforms stay green instead of temporarily switching to yellow.
  if (typeof draw !== "function" || typeof state === "undefined") return;

  const ROI_FILL = "rgba(39,147,104,.16)";
  const ROI_STROKE = "#31a87a";
  const baseDraw = draw;

  draw = () => {
    const roiDraft = state.mode === "roi" && state.drawing ? state.drawing : null;
    const gesture = state.unifiedTransformGesture;
    const transformingRoi = gesture?.target?.kind === "roi";

    // Suppress the yellow draft/active branches in the base renderer while
    // preserving all of its selection handles, labels and other overlays.
    if (roiDraft) state.drawing = null;
    if (transformingRoi) gesture.target.kind = "roi-green-render";

    try {
      baseDraw();
    } finally {
      if (transformingRoi) gesture.target.kind = "roi";
      if (roiDraft) state.drawing = roiDraft;
    }

    if (roiDraft && state.sourceImage) {
      const rect = normalizedRect(roiDraft.start, roiDraft.end);
      drawDisplayOverlay(rect, ROI_FILL, ROI_STROKE, "");
      updateSaveAction();
    }
  };

  draw();
})();
