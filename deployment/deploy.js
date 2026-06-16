const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');
require('dotenv').config();

const BUCKET   = 'learning-language-mangox';
const MC_ALIAS = 'r2-mangox';
const BASE_URL = process.env.R2_PUBLIC_URL || 'https://pub-9f844fdf34684f6ca0651880b2769046.r2.dev';
const ROOT     = path.dirname(__dirname);

// ── helpers ──────────────────────────────────────────────────────────────────

function mc(args) {
  execSync(`mc ${args}`, { stdio: 'inherit' });
}

function buildManifest(outputDir) {
  const clips   = [];
  const entries = fs.readdirSync(outputDir, { withFileTypes: true });
  const dirs    = entries.filter(e => e.isDirectory());

  for (const dir of dirs) {
    const slug    = dir.name;
    const clipDir = path.join(outputDir, slug);
    const videoPath = path.join(clipDir, 'video.mp4');
    if (!fs.existsSync(videoPath)) continue;

    const stat = fs.statSync(videoPath);
    const clip = {
      slug,
      title:     slug,
      mp4Url:    `${BASE_URL}/output/${encodeURIComponent(slug)}/video.mp4`,
      createdAt: stat.mtimeMs,
      updatedAt: stat.mtimeMs,
    };

    const thumbPath = path.join(clipDir, 'thumb.jpg');
    if (fs.existsSync(thumbPath)) {
      clip.thumbUrl = `${BASE_URL}/output/${encodeURIComponent(slug)}/thumb.jpg`;
    }

    const partsDir = path.join(clipDir, 'parts');
    if (fs.existsSync(partsDir)) {
      const transcripts = fs.readdirSync(partsDir)
        .filter(f => f.endsWith('_transcript.json'))
        .sort()
        .map(f => `${BASE_URL}/output/${encodeURIComponent(slug)}/parts/${f}`);
      if (transcripts.length) {
        clip.hasTranscript  = true;
        clip.transcriptUrls = transcripts;
      }
    }

    clips.push(clip);
  }
  return clips;
}

// ── main ─────────────────────────────────────────────────────────────────────

function main() {
  const outputDir = path.join(ROOT, 'output');
  const args      = process.argv.slice(2);

  // 1. Build & upload manifest.json
  console.log('\n📋 Building manifest...');
  const manifest     = buildManifest(outputDir);
  const manifestPath = path.join(ROOT, 'manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log(`   ${manifest.length} clips found`);
  mc(`cp --attr "Cache-Control=no-cache" "${manifestPath}" ${MC_ALIAS}/${BUCKET}/manifest.json`);

  if (args.includes('--manifest-only')) {
    console.log('\n✅ Done! (manifest only)');
    console.log(`🌐 ${BASE_URL}/all-video.html`);
    return;
  }

  // 2. Upload all-video.html
  console.log('\n📄 Uploading HTML...');
  mc(`cp --attr "Cache-Control=no-cache" "${path.join(ROOT, 'all-video.html')}" ${MC_ALIAS}/${BUCKET}/all-video.html`);

  // 3. Mirror output/ → R2
  console.log('\n📁 Mirroring output/...');
  mc(`mirror --overwrite "${outputDir}" ${MC_ALIAS}/${BUCKET}/output`);

  console.log('\n✅ Done!');
  console.log(`🌐 ${BASE_URL}/all-video.html`);
}

main();
