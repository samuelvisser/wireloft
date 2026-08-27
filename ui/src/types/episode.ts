import {createSelectRegistry} from "../utils/selectRegistry";

export enum EpisodePublishStatus {
    scheduled = 'Scheduled',
    delayed = 'Delayed',
    live = 'Live',
    dwProcessing = 'Processing on Dailywire',
    publishedWithCountdown = 'Published on Dailywire (with countdown)',
    publishedFinal = 'Published on Dailywire',
}

export const EpisodeTypeReg = createSelectRegistry("EpisodeType", {
  'ep':   { label: "Episode", help: "Normal episode in the show" },
  'ep-extra':   { label: "Ep. Extra", help: "Auxiliary content for a specific episode" },
  'trailer':   { label: "Trailer", help: "Trailer for show or auxiliary content" },
  'aux':   { label: "Auxiliary", help: "Auxiliary content for the show" },
});

/** Wire values (snake_case, as sent by the backend) of an episode's publishStatus. */
export const PUBLISH_STATUS_LABELS: Record<string, string> = {
    scheduled: 'Scheduled',
    delayed: 'Officially delayed',
    live: 'Live',
    dw_processing: 'Processing on DailyWire',
    published_with_countdown: 'Published (still contains countdown)',
    published_final: 'Published',
}