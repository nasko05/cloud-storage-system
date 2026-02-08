import React from 'react';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import DescriptionIcon from '@mui/icons-material/Description';
import TableChartIcon from '@mui/icons-material/TableChart';
import AudioFileIcon from '@mui/icons-material/AudioFile';
import VideoFileIcon from '@mui/icons-material/VideoFile';

export function DynamicRenderedIcon({ filename, iconProps }: { filename: string, iconProps: React.ComponentProps<typeof InsertDriveFileRoundedIcon> }): React.ReactNode {
    const extension = filename.split('.').pop();
    switch (extension) {
        case 'pdf':
            return React.createElement(PictureAsPdfIcon, iconProps);
        case 'docx':
            return React.createElement(DescriptionIcon, iconProps);
        case 'doc':
            return React.createElement(DescriptionIcon, iconProps);
        case 'xls':
            return React.createElement(TableChartIcon, iconProps);
        case 'xlsx':
            return React.createElement(TableChartIcon, iconProps);
        case 'mp3':
            return React.createElement(AudioFileIcon, iconProps);
        case 'mp4':
            return React.createElement(VideoFileIcon, iconProps);
        case 'mpg':
            return React.createElement(VideoFileIcon, iconProps);
        case 'mpeg':
            return React.createElement(VideoFileIcon, iconProps);
        case 'mov':
            return React.createElement(VideoFileIcon, iconProps);
        case 'avi':
            return React.createElement(VideoFileIcon, iconProps);
        case 'wmv':
            return React.createElement(VideoFileIcon, iconProps);
        case 'flv':
            return React.createElement(VideoFileIcon, iconProps);
        case 'mkv':
            return React.createElement(VideoFileIcon, iconProps);
        default:
            return React.createElement(InsertDriveFileRoundedIcon, iconProps);
    }
}