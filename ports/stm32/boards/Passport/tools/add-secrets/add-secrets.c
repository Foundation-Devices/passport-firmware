// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <libgen.h>

#define EXTENSION   "-secrets"

static char *bootloader;
static char *secrets;
static bool help;
static bool debug_log_level;

static void usage(
    char *name
)
{
    printf("Usage:%s\n", name);
    printf("\t-d: debug logging\n"
           "\t-b <bootloader binary>: full path to bootloader binary file\n"
           "\t-s <secrets binary>: full path to secrets binary file\n"
           "\t-h: this message\n"
          );
    exit(1);
}

static void process_args(
    int argc,
    char **argv
)
{
    int c = 0;

    while ((c = getopt(argc, argv, "dhb:s:")) != -1)
    {
        switch (c)
        {
            case 'b':
                bootloader = optarg;
            break;
            case 's':
                secrets = optarg;
            break;
            case 'd':
                debug_log_level = true;
            break;
             case 'h':
                help = true;
            break;
            default:
                usage(argv[0]);
            break;
        }
    }
}

static size_t read_file(
    char *path,
    uint8_t **buffer
)
{
    uint32_t ret = 0;
    struct stat info;
    FILE *fp;

    fp = fopen(path, "r");
    if (fp == NULL)
    {
        printf("failed to open %s\n", path);
        return 0;
    }

    stat(path, &info);
    *buffer = (uint8_t*)calloc(1, info.st_size + sizeof(ulong));
    if (*buffer == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }

    ret = fread(*buffer, 1, info.st_size, fp);
    if (ret != info.st_size)
        free(*buffer);
    else
        ret = info.st_size;

out:
    fclose(fp);
    return ret;
}

static void add_secrets(
    char *bl,
    char *secrets
)
{
    size_t ret = 0;
    size_t bl_len;
    size_t secrets_len;
    uint8_t *bl_buf = NULL;
    uint8_t *secrets_buf = NULL;
    FILE *fp = NULL;
    char *outfile;
    char *path;
    char *filename;
    char *file;
    char *tmp;

    if (bl == NULL)
    {
        printf("bootloader not specified\n");
        return;
    }
    tmp = strdup(bl);

    filename = basename(tmp);
    if (filename == NULL)
    {
        printf("basename() failed\n");
        return;
    }

    path = dirname(tmp);
    if (path == NULL)
    {
        printf("dirname() failed\n");
        return;
    }

    file = strtok(filename, ".");
    if (file == NULL)
    {
        printf("strtok() failed\n");
        return;
    }

    outfile = (char *)calloc(1, strlen(bl) + strlen(EXTENSION) + 1);
    if (outfile == NULL)
    {
        printf("insufficient memory\n");
        return;
    }

    sprintf(outfile, "%s/%s%s.bin", path, file, EXTENSION);

    if (debug_log_level)
        printf("Reading %s...", bl);
    bl_len = read_file(bl, &bl_buf);
    if (bl_len == 0)
    {
        printf("file %s has no data\n", bl);
        return;
    }
    if (debug_log_level)
        printf("done\n");

    if (debug_log_level)
        printf("Reading %s...", secrets);
    secrets_len = read_file(secrets, &secrets_buf);
    if (secrets_len == 0)
    {
        printf("file %s has no data\n", secrets);
        return;
    }
    if (debug_log_level)
        printf("done\n");

    fp = fopen(outfile, "wb");
    if (fp == NULL)
    {
        printf("failed to open %s\n", outfile);
        goto out;
    }

    if (debug_log_level)
        printf("Writing bootloader to %s - ", outfile);
    ret = fwrite(bl_buf, 1, bl_len, fp);
    if (ret != bl_len)
    {
        unlink(outfile);
        printf("\n%s write failed - check disk space\n", outfile);
        goto out;
    }
    if (debug_log_level)
        printf("done\n");

    if (debug_log_level)
        printf("Writing secrets to %s - ", outfile);
    ret = fwrite(secrets_buf, 1, secrets_len, fp);
    if (ret != secrets_len)
    {
        unlink(outfile);
        printf("\n%s write failed - check disk space\n", outfile);
        goto out;
    }
    if (debug_log_level)
        printf("done\n");


out:
    free(bl_buf);
    free(secrets_buf);
    free(outfile);
    free(tmp);
    fclose(fp);
}

int main(int argc, char *argv[])
{
    process_args(argc, argv);

    if (help)
        usage(argv[0]);

    add_secrets(bootloader, secrets);

    exit(0);
}
