const PptxGenJS = require("pptxgenjs");

const out = process.argv[2];
if (!out) {
  process.stderr.write("usage: node build_deck.js <out.pptx>\n");
  process.exit(2);
}

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_16x9";
const slide = pptx.addSlide();
slide.addText("Presentation qualification core proof", {
  x: 0.5, y: 0.8, w: 9, h: 0.8, fontSize: 28
});
slide.addText(
  "PptxGenJS-authored slide rendered by LibreOffice and Poppler inside a locked-down kernel pod",
  { x: 0.5, y: 1.8, w: 9, h: 1.2, fontSize: 14 }
);
slide.addText(new Date().toISOString(), { x: 0.5, y: 3.4, w: 6, h: 0.5, fontSize: 12 });

pptx
  .writeFile({ fileName: out })
  .then(() => process.exit(0))
  .catch((err) => {
    process.stderr.write(String((err && err.message) || err) + "\n");
    process.exit(1);
  });
