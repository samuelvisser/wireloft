import {useEffect, useMemo, useRef} from "react";
import DailywireShowCard from "./DailywireShowCard";
import {useDailywireShow} from "../../lib/queries";
import ReadMore from "../../utils/ReadMore";
import {Controller, SubmitHandler, useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {
    ShowCreateFormSchema,
    ShowCreatePayloadSchema,
    ShowDailywireSchema,
    type ShowCreateFormIn, ShowCreatePayloadOut, ShowCreatePayloadIn,
} from "../../types/schemas/show";
import {EpisodeIdentifierReg, EpisodeIdentifierValue, ShowTypeReg, ShowTypeValue} from "../../types/show";
import Select from "react-select";
import {UseQueryResult} from "@tanstack/react-query";
import {SeasonCreateBundleOut, SeasonCreateBundleSchema} from "../../types/schemas/show_with_profiles";

type Props = {
    value: Partial<ShowCreatePayloadIn>
    onChange: (v: Partial<ShowCreatePayloadIn>) => void;
    onSubmit: (v: ShowCreatePayloadOut) => void;
    onSeasonsSubmit: (seasons: SeasonCreateBundleOut[]) => void;
    onContinue: () => void;
    onCancel: () => void;
};

export default function ChooseShowStep({value, onChange, onSubmit: onSubmitParent, onSeasonsSubmit, onContinue, onCancel,}: Props) {
    // --- Form: only user-editable fields are in this schema
    const form = useForm<ShowCreateFormIn>({
        resolver: zodResolver(ShowCreateFormSchema),
        mode: "onBlur",
        defaultValues: value,
    });

    const {
        register,
        setValue,
        setError,
        watch,
        control,
        handleSubmit,
        formState: {isSubmitting, errors},
    } = form;

    // --- Subscribe to ALL form changes
    useEffect(() => {
        const subscription = watch((values: ShowCreatePayloadIn) => {
            onChange(values); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    // --- Watch the URL and extract the slug when valid
    const watchedUrl = watch("url");
    const urlParsed = useMemo(() => ShowCreateFormSchema.shape.url.safeParse(watchedUrl ?? ""), [watchedUrl]);
    const slugFromUrl: string | undefined = useMemo(() => {
        if (!urlParsed.success) return undefined;
        try {
            const parsedUrl = new URL(urlParsed.data ?? "");
            const path: string = parsedUrl.pathname;
            if (!path.startsWith("/show/")) return undefined;
            const s: string = path.slice("/show/".length).split("/")[0];
            return s || undefined;
        } catch {
            return undefined;
        }
    }, [urlParsed]);

    // --- Watch the type and set the episodeIdentifier to numbered when the type is series
    const watchedType = watch("type");
    useEffect(() => {
        if (watchedType === ShowTypeReg.Enum.series) {
            setValue("episodeIdentifier", EpisodeIdentifierReg.Enum.numbered, {shouldValidate: true, shouldDirty: true});
        }
    }, [watchedType, setValue]);

    // --- Fetch DailyWire data using the slug
    const lastPrefilledUrlRef = useRef<string | undefined>(value.url);
    const dw: UseQueryResult<any> = useDailywireShow(slugFromUrl);

    // --- Prefill defaults for type & episodeIdentifier from the external API when available
    useEffect(() => {
        if (!dw.data) return;
        const currentUrl = watchedUrl ?? "";
        if (currentUrl === (lastPrefilledUrlRef.current ?? "")) return;

        const inferredType: ShowTypeValue | "" = ShowTypeReg.normalize(dw.data.probableShowType) ?? "";
        const inferredEpisodeId: EpisodeIdentifierValue | "" = EpisodeIdentifierReg.normalize(dw.data.probableEpisodeIdentification) ?? "";

        setValue("type", inferredType, {shouldValidate: true, shouldDirty: true});
        setValue("episodeIdentifier", inferredEpisodeId, {shouldValidate: true, shouldDirty: true});

        // Remember that we prefetched for this URL to prevent reapplying on mount/reload
        lastPrefilledUrlRef.current = currentUrl;
    }, [dw.data, watchedUrl, setValue]);

    // --- Submit handler
    const onSubmit: SubmitHandler<ShowCreateFormIn> = (formOnly: ShowCreateFormIn) => {
        // Gather/normalize derived fields from the API response
        const anyData = dw.data as any;

        // Validate dailywire data
        const dailywireParsed = ShowDailywireSchema.safeParse({
            dwId: anyData?.id,
            slug: slugFromUrl,
            ...anyData
        });

        // Validate seasons
        const seasonsRaw: any[] = Array.isArray(anyData?.seasons) ? anyData.seasons : [];
        const seasonsParsed = SeasonCreateBundleSchema.array().safeParse(
            seasonsRaw.map((s: any) => ({
                dwId: s?.id ?? '',
                ...s
            }))
        );

        if (!dailywireParsed.success) {
            const first = dailywireParsed.error.issues[0];
            setError("url", {
                type: "validate",
                message: "Dailywire api returned invalid data: " + (first?.message ?? "Invalid data from dailywire")
            });
            throw dailywireParsed.error;
        }

        if (!seasonsParsed.success) {
            const first = seasonsParsed.error.issues[0];
            setError("url", {
                type: "validate",
                message: "Dailywire seasons invalid: " + (first?.message ?? "Invalid seasons from DailyWire"),
            });
            throw seasonsParsed.error;
        }

        // Validate final payload. We do not save anything yet (only in the final widget step)
        const payload = ShowCreatePayloadSchema.parse({...formOnly, ...dailywireParsed.data});
        onSeasonsSubmit(seasonsParsed.data);
        onSubmitParent(payload);
        onContinue();
    }

    // --- Render
    return (
        <form className="form" onSubmit={handleSubmit(onSubmit)} noValidate>
            {errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}
            <div className="form-row">
                <label htmlFor="show-url">Daily Wire show URL</label>
                <input
                    id="show-url"
                    className="input"
                    type="url"
                    inputMode="url"
                    placeholder="https://www.dailywire.com/show/the-ben-shapiro-show"
                    {...register("url")}
                    aria-invalid={!!errors.url}
                    aria-describedby={errors.url ? "show-url-validate" : undefined}
                />
                {errors.url && (
                    <div id="show-url-validate" className="error" role="alert" aria-live="polite">
                        {errors.url.message as string}
                    </div>
                )}
                <div id="url-help" className="help">
                    Must be on dailywire.com, include /show/, and a show name.
                </div>
            </div>

            {/* Preview fetched DailyWire show info */}
            {urlParsed.success && (
                <>
                    <div className="form-row" aria-live="polite">
                        <DailywireShowCard showSlug={slugFromUrl}/>
                    </div>

                    {/* Show type selector under the card */}
                    {dw.isSuccess && !!dw.data && (
                        <>
                            <div className="form-row">
                                <label htmlFor="show-type">Show type</label>
                                <Controller
                                    control={control}
                                    name="type"
                                    render={({field}) => (
                                        <Select
                                            inputId="show-type"
                                            options={ShowTypeReg.options}
                                            value={ShowTypeReg.options.find(o => o.value === field.value) ?? null}
                                            onChange={(opt) => field.onChange(opt?.value ?? "")}
                                            onBlur={field.onBlur}
                                            aria-invalid={!!errors.type}
                                            aria-describedby={errors.type ? 'show-type-errors' : 'show-type-help'}
                                            isClearable
                                        />

                                    )}
                                />
                                {errors.type && (
                                    <div id="show-type-errors" className="error" role="alert" aria-live="polite">
                                        {errors.type.message as string}
                                    </div>
                                )}
                                <div className="help" id="show-type-help">
                                    <ReadMore summary={<span>Why do I need to choose this?</span>}>
                                        Selecting the correct show type helps WireLoft apply sensible defaults for how
                                        episodes are
                                        grouped and presented.<br/><br/>
                                        Though WireLoft tries to guess the show type automatically based on various
                                        factors, Dailywire unfortunately does not provide a reliable way to determine
                                        this. If you're unsure, select "Podcast".
                                    </ReadMore>
                                </div>
                            </div>

                            {/* Episode identification selector (only for Podcast) */}
                            {watch("type") === ShowTypeReg.Enum.podcast && (
                                <div className="form-row">
                                    <label htmlFor="episode-identification">Episode identification</label>


                                    <Controller
                                        control={control}
                                        name="episodeIdentifier"
                                        render={({field}) => (
                                            <Select
                                                inputId="show-type"
                                                options={EpisodeIdentifierReg.options}
                                                value={EpisodeIdentifierReg.options.find(o => o.value === field.value) ?? null}
                                                onChange={(opt) => field.onChange(opt?.value ?? "")}
                                                onBlur={field.onBlur}
                                                aria-invalid={!!errors.episodeIdentifier}
                                                aria-describedby={errors.episodeIdentifier ? 'episode-identification-errors' : 'episode-identification-help'}
                                                isClearable
                                            />
                                        )}
                                    />
                                    {errors.episodeIdentifier && (
                                        <div id="episode-identification-errors" className="error" role="alert"
                                             aria-live="polite">
                                            {errors.episodeIdentifier.message as string}
                                        </div>
                                    )}
                                    <div className="help" id="episode-identification-help">
                                        <ReadMore summary={<span>How are episodes in this show identified?</span>}>
                                            Some shows identify their episodes by a number. In this case, WireLoft
                                            expects to see a string
                                            "Ep. " in the title. The number that follows it is taken as the episode
                                            number. Episodes without
                                            this format will be regarded as auxiliary content.
                                            <br/>
                                            <br/>
                                            Sometimes however, shows use a date-based format. In this case, the episodes
                                            are identified simply
                                            by their release date.
                                            <br/>
                                            <br/>
                                            If you're unsure, select "Date-based".
                                        </ReadMore>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </>
            )}

            <div className="actions">
                <input type="submit" className="btn btn-primary" value="Continue" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>
                    Cancel
                </button>
            </div>
        </form>
    );
}