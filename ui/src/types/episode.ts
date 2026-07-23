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