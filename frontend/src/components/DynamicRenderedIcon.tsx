import React from 'react';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import DescriptionIcon from '@mui/icons-material/Description';
import TableChartIcon from '@mui/icons-material/TableChart';
import AudioFileIcon from '@mui/icons-material/AudioFile';
import VideoFileIcon from '@mui/icons-material/VideoFile';
import { getExtension } from '../service/fileUtils';

export function DynamicRenderedIcon({ filename, iconProps }: { filename: string, iconProps: React.ComponentProps<typeof InsertDriveFileRoundedIcon> }): React.ReactNode {
    const extension = getExtension(filename);
    switch (extension) {
        case 'pdf':
            return <PictureAsPdfIcon {...iconProps} />;
        case 'docx':
        case 'doc':
            return <DescriptionIcon {...iconProps} />;
        case 'xls':
        case 'xlsx':
            return <TableChartIcon {...iconProps} />;
        case 'mp3':
            return <AudioFileIcon {...iconProps} />;
        case 'mp4':
        case 'mpg':
        case 'mpeg':
        case 'mov':
        case 'avi':
        case 'wmv':
        case 'flv':
        case 'mkv':
            return <VideoFileIcon {...iconProps} />;
        default:
            return <InsertDriveFileRoundedIcon {...iconProps} />;
    }
}
