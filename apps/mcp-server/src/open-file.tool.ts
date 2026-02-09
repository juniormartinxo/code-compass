import { Injectable } from '@nestjs/common';

import { FileService } from './file.service';
import { OpenFileOutput } from './types';

@Injectable()
export class OpenFileTool {
  constructor(private readonly fileService: FileService) {}

  async execute(rawInput: unknown): Promise<OpenFileOutput> {
    return this.fileService.openRange(rawInput);
  }
}
