<script lang="ts">
  import { motion } from "@humanspeak/svelte-motion";

  type Props = {
    configured: boolean;
    busy?: boolean;
    error?: string;
    biometricAvailable?: boolean;
    preview?: boolean;
    onSubmit?: (password: string, confirmation?: string) => Promise<void> | void;
    onBiometric?: () => Promise<void> | void;
  };

  let {
    configured,
    busy = false,
    error = "",
    biometricAvailable = false,
    preview = false,
    onSubmit = () => {},
    onBiometric = () => {}
  }: Props = $props();

  let password = $state("");
  let confirmation = $state("");
  let localError = $state("");
  let submitting = $state(false);

  let title = $derived(configured ? "Enter the vault" : "Create your vault");
  let actionLabel = $derived(configured ? "Unlock AETHER-STREAM" : "Initialize encrypted vault");
  let visibleError = $derived(error || localError);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    localError = "";

    if (!configured && password.length < 10) {
      localError = "Use at least 10 characters for the vault passphrase.";
      return;
    }
    if (!configured && password !== confirmation) {
      localError = "The passphrases do not match.";
      return;
    }
    if (!password) {
      localError = "Enter your vault passphrase.";
      return;
    }

    submitting = true;
    try {
      await onSubmit(password, configured ? undefined : confirmation);
      password = "";
      confirmation = "";
    } catch (submitError) {
      password = "";
      confirmation = "";
      localError = submitError instanceof Error ? submitError.message : "Unlock failed.";
    } finally {
      submitting = false;
    }
  }

  async function biometric() {
    localError = "";
    submitting = true;
    try {
      await onBiometric();
    } catch (biometricError) {
      localError = biometricError instanceof Error ? biometricError.message : "Biometric unlock failed.";
    } finally {
      submitting = false;
    }
  }
</script>

<div class="relative grid min-h-screen place-items-center overflow-hidden bg-[#07090e] px-5 py-10 text-white">
  <div class="pointer-events-none absolute inset-0 [background-image:linear-gradient(rgba(255,255,255,0.022)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.022)_1px,transparent_1px)] [background-size:64px_64px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_78%)]"></div>
  <div class="lock-orbit lock-orbit-one pointer-events-none absolute h-[38rem] w-[38rem] rounded-full border border-cyan-200/[0.08]"></div>
  <div class="lock-orbit lock-orbit-two pointer-events-none absolute h-[25rem] w-[25rem] rounded-full border border-violet-200/[0.08]"></div>
  <div class="pointer-events-none absolute -left-32 top-1/4 h-80 w-80 rounded-full bg-cyan-300/10 blur-[120px]"></div>
  <div class="pointer-events-none absolute -right-40 bottom-1/4 h-96 w-96 rounded-full bg-violet-400/10 blur-[140px]"></div>

  <motion.div
    initial={{ opacity: 0, y: 14, scale: 0.98 }}
    animate={{ opacity: 1, y: 0, scale: 1 }}
    transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
    class="relative w-full max-w-[26rem]"
  >
    <div class="mb-8 text-center">
      <div class="mx-auto mb-6 grid h-14 w-14 place-items-center rounded-2xl border border-cyan-200/20 bg-cyan-200/[0.08] shadow-[0_0_70px_rgba(103,232,249,0.18)]">
        <svg class="h-7 w-7 text-cyan-100" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <rect x="5" y="10" width="14" height="10" rx="2"></rect>
          <path d="M8 10V7a4 4 0 0 1 8 0v3"></path>
          <path d="M12 14v2"></path>
        </svg>
      </div>
      <div class="font-mono text-[0.62rem] uppercase tracking-[0.28em] text-cyan-200/65">AETHER-STREAM / secure enclave</div>
      <h1 class="mt-4 text-3xl font-medium tracking-[-0.05em] text-white">{title}</h1>
      <p class="mx-auto mt-3 max-w-sm text-sm leading-6 text-slate-500">
        {#if configured}
          Your queue, history, and intercepted media are sealed locally until you authenticate.
        {:else}
          Create the only credential that can open this local-first transfer plane.
        {/if}
      </p>
    </div>

    <div class="rounded-3xl border border-white/[0.1] bg-white/[0.045] p-5 shadow-[0_28px_100px_-40px_rgba(0,0,0,0.95)] backdrop-blur-2xl sm:p-6">
      <form onsubmit={submit}>
        <label class="block font-mono text-[0.6rem] uppercase tracking-[0.18em] text-slate-500" for="vault-password">
          {configured ? "Vault passphrase" : "New vault passphrase"}
        </label>
        <div class="mt-2 flex items-center rounded-xl border border-white/10 bg-black/20 px-3 transition focus-within:border-cyan-200/50 focus-within:shadow-[0_0_0_4px_rgba(103,232,249,0.07)]">
          <svg class="h-4 w-4 shrink-0 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M8 10V7a4 4 0 0 1 8 0v3"></path>
          </svg>
          <input
            id="vault-password"
            class="w-full bg-transparent px-3 py-3.5 text-sm tracking-[0.18em] text-white outline-none placeholder:tracking-normal placeholder:text-slate-700"
            type="password"
            bind:value={password}
            placeholder="••••••••••••"
            autocomplete={configured ? "current-password" : "new-password"}
            disabled={busy || submitting}
            aria-describedby="vault-help"
          />
        </div>

        {#if !configured}
          <label class="mt-4 block font-mono text-[0.6rem] uppercase tracking-[0.18em] text-slate-500" for="vault-confirmation">Confirm passphrase</label>
          <div class="mt-2 flex items-center rounded-xl border border-white/10 bg-black/20 px-3 transition focus-within:border-cyan-200/50 focus-within:shadow-[0_0_0_4px_rgba(103,232,249,0.07)]">
            <svg class="h-4 w-4 shrink-0 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
              <path d="M12 3 5 6v5c0 4.6 2.9 8.2 7 10 4.1-1.8 7-5.4 7-10V6l-7-3Z"></path><path d="m9 12 2 2 4-4"></path>
            </svg>
            <input
              id="vault-confirmation"
              class="w-full bg-transparent px-3 py-3.5 text-sm tracking-[0.18em] text-white outline-none placeholder:tracking-normal placeholder:text-slate-700"
              type="password"
              bind:value={confirmation}
              placeholder="repeat passphrase"
              autocomplete="new-password"
              disabled={busy || submitting}
            />
          </div>
        {/if}

        <p id="vault-help" class="mt-3 font-mono text-[0.58rem] leading-5 text-slate-700">
          Argon2id verifier · SQLCipher queue · no telemetry
        </p>

        {#if visibleError}
          <div class="mt-4 flex gap-2 rounded-xl border border-rose-300/20 bg-rose-300/[0.07] px-3 py-2.5 text-xs leading-5 text-rose-100" role="alert">
            <span class="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-300"></span>
            {visibleError}
          </div>
        {/if}

        <button
          class="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-200 px-4 py-3.5 text-sm font-semibold text-[#071014] shadow-[0_14px_36px_-16px_rgba(103,232,249,0.9)] transition hover:-translate-y-0.5 hover:bg-cyan-100 disabled:cursor-wait disabled:opacity-50"
          type="submit"
          disabled={busy || submitting}
        >
          {#if busy || submitting}
            <span class="h-4 w-4 animate-spin rounded-full border-2 border-[#071014]/30 border-t-[#071014]"></span>
            Verifying locally…
          {:else}
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 3v18M3 12h18"></path>
            </svg>
            {actionLabel}
          {/if}
        </button>
      </form>

      <div class="my-5 flex items-center gap-3 text-[0.58rem] uppercase tracking-[0.2em] text-slate-700">
        <span class="h-px flex-1 bg-white/[0.07]"></span><span>or</span><span class="h-px flex-1 bg-white/[0.07]"></span>
      </div>

      <button
        class="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] px-4 py-3 text-sm font-medium text-slate-300 transition hover:border-violet-200/30 hover:bg-violet-200/[0.06] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
        type="button"
        disabled={!biometricAvailable || busy || submitting}
        onclick={biometric}
        title={biometricAvailable ? "Use the device biometric authenticator" : "Native biometric adapter not configured yet"}
      >
        <svg class="h-4 w-4 text-violet-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v3"></path><circle cx="12" cy="12" r="3"></circle>
        </svg>
        Unlock with biometrics
        {#if !biometricAvailable}<span class="font-mono text-[0.55rem] text-slate-700">native adapter pending</span>{/if}
      </button>
    </div>

    <div class="mt-6 flex items-center justify-center gap-2 font-mono text-[0.58rem] uppercase tracking-[0.16em] text-slate-700">
      <span class="h-1.5 w-1.5 rounded-full bg-emerald-300/80"></span>
      Device-bound · sealed at rest · zero telemetry
    </div>
    {#if preview}
      <div class="mt-4 rounded-xl border border-amber-200/10 bg-amber-200/[0.04] px-3 py-2 text-center font-mono text-[0.56rem] leading-5 text-amber-100/50">
        Browser preview mode: use any four or more characters to inspect the interface. Tauri uses Argon2id + SQLCipher.
      </div>
    {/if}
  </motion.div>
</div>

<style>
  .lock-orbit-one { animation: orbit 32s linear infinite; }
  .lock-orbit-two { animation: orbit-reverse 22s linear infinite; }

  @keyframes orbit {
    from { transform: rotate(0deg) scale(1); }
    50% { transform: rotate(180deg) scale(1.04); }
    to { transform: rotate(360deg) scale(1); }
  }

  @keyframes orbit-reverse {
    from { transform: rotate(360deg) scale(1.04); }
    50% { transform: rotate(180deg) scale(0.96); }
    to { transform: rotate(0deg) scale(1.04); }
  }

  @media (prefers-reduced-motion: reduce) {
    .lock-orbit-one,
    .lock-orbit-two { animation: none; }
  }
</style>
