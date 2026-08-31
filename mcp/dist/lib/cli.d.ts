export interface IxResult {
    ok: boolean;
    stdout: string;
    stderr: string;
    durationMs: number;
}
export declare function stripHeader(raw: string): string;
export declare function runIx(args: string[], opts?: {
    timeout?: number;
}): Promise<IxResult>;
/**
 * The CLI's own structured error, when a run that exited non-zero still printed
 * one.
 *
 * `ix` reports a refusal as `{"error": "<slug>", "message": "..."}` on stdout
 * and exits non-zero to match, so the exit code alone cannot tell a broken
 * install from a target that simply is not in the graph — the body can, and it
 * is the more specific of the two. Returns null when the run succeeded, printed
 * nothing, or printed something that is not one of those records, leaving the
 * caller's existing error path untouched.
 */
export declare function cliStructuredError(result: IxResult): {
    code: string;
    message: string;
} | null;
//# sourceMappingURL=cli.d.ts.map