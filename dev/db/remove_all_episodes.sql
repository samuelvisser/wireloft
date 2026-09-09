DELETE FROM media_items_episode WHERE show_id = :show_id;

DELETE FROM metadata WHERE parent_table = 'shows' AND parent_id = :show_id;
