/** Decorative floating stack of four chip layers, drawn with CSS 3D transforms. */
const LAYERS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

export default function Hero3D() {
  return (
    <div className="hero3d" aria-hidden="true">
      <div className="h3-shadow" />
      <div className="h3-stack">
        {LAYERS.map((c, i) => (
          <div key={i} className="h3-slab" style={{ ["--c" as string]: c, ["--i" as string]: i }}>
            <span className="s s1" />
            <span className="s s3" />
            <span className="top" />
          </div>
        ))}
      </div>
    </div>
  );
}
