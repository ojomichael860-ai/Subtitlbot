import os
from PIL import Image, ImageDraw, ImageFont
import moviepy.editor as mp

def wrap_text(text, font, max_width):
    """Utility to break text down into multiple lines matching video width constraints."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        # Calculate width using modern bbox
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return '\n'.join(lines)

def burn_captions_to_video(video_path, text, output_path):
    """Processes video frames and burns a bold subtitle background caption layer."""
    try:
        # 1. Open the original video
        video_clip = mp.VideoFileClip(video_path)
        
        # 2. Extract dimensions
        w, h = video_clip.size
        
        # 3. Create a text image layer overlay using Pillow
        caption_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(caption_img)
        
        # Select responsive font configurations
        font_size = int(w * 0.05)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
            
        # Format word line boundaries wrapping at 85% of total width
        formatted_text = wrap_text(text, font, int(w * 0.85))
        
        # Measure structural metrics
        bbox = draw.texttextbox if hasattr(draw, 'texttextbox') else draw.textbbox
        text_bbox = bbox((0, 0), formatted_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        
        # Position variables (Lower center alignment)
        x = (w - text_w) // 2
        y = int(h * 0.75) - (text_h // 2)
        
        # Draw semi-transparent dark background block behind text for high readability
        padding = 15
        draw.rectangle(
            [x - padding, y - padding, x + text_w + padding, y + text_h + padding],
            fill=(0, 0, 0, 160)
        )
        
        # Draw clean crisp white font captions
        draw.text((x, y), formatted_text, fill=(255, 255, 255, 255), font=font)
        
        # Save temp overlay frame
        temp_overlay_path = f"overlay_{os.path.basename(video_path)}.png"
        caption_img.save(temp_overlay_path)
        
        # 4. Composite layout using MoviePy
        overlay_clip = (mp.ImageClip(temp_overlay_path)
                        .set_duration(video_clip.duration)
                        .set_pos(("center", "center")))
        
        final_video = mp.CompositeVideoClip([video_clip, overlay_clip])
        
        # Write output video using highly compressed, Render-friendly CPU threads
        final_video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            threads=1, 
            logger=None
        )
        
        # Close clip streams immediately to release RAM 
        video_clip.close()
        final_video.close()
        
        if os.path.exists(temp_overlay_path):
            os.remove(temp_overlay_path)
            
        return True, None
    except Exception as e:
        return False, str(e)
