import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: 'index.html',   // SPA fallback for LINE WebView
			precompress: false,
			strict: true,
		}),
		// LIFF は LINE WebView で動くため SSR 不要
		prerender: { handleMissingId: 'warn' },
	}
};

export default config;
