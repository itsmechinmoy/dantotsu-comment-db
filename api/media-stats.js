import fs from 'fs';
import path from 'path';
import csv from 'csv-parser';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  try {
    const csvPath = path.join(process.cwd(), 'public', 'dantotsu_global_db.csv');
    
    const stats = new Map();
    
    await new Promise((resolve, reject) => {
      fs.createReadStream(csvPath)
        .pipe(csv({ separator: '\t' }))
        .on('data', (row) => {
          if (row.deleted === '1') return;
          
          const mediaId = row.media_id;
          if (!mediaId) return;
          
          if (!stats.has(mediaId)) {
            stats.set(mediaId, {
              media_id: mediaId,
              total_comments: 0,
              reply_count: 0,
              top_level_comments: 0,
              unique_users: new Set()
            });
          }
          
          const record = stats.get(mediaId);
          record.total_comments++;
          record.unique_users.add(row.user_id);
          
          if (row.parent_comment_id && row.parent_comment_id !== 'NULL' && row.parent_comment_id !== '') {
            record.reply_count++;
          } else {
            record.top_level_comments++;
          }
        })
        .on('end', resolve)
        .on('error', reject);
    });
    
    const result = Array.from(stats.values()).map(record => ({
      media_id: record.media_id,
      total_comments: record.total_comments,
      reply_count: record.reply_count,
      top_level_comments: record.top_level_comments,
      unique_users: record.unique_users.size
    }));
    
    result.sort((a, b) => b.total_comments - a.total_comments);
    
    res.status(200).json({ 
      success: true, 
      count: result.length,
      data: result 
    });
    
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
}
